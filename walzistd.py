#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging
from collections import defaultdict

from messages import Upload, Request
from util import even_split
from peer import Peer

class WalziStd(Peer):
    def post_init(self):
        self.regular_slots = set()
        self.optimistic_unchoke = set()

        self.num_slots = min(3, self.up_bw) # ASSUMPTION that we set the number of unchoke slots to 4 or less if we can't even provide that much uploading

        print(("post_init(): %s here!" % self.id))
    
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        num_pieces = len(self.pieces)

        needed = lambda pid: self.pieces[pid] < self.conf.blocks_per_piece
        needed_pieces_list = filter(needed, [x for x in range(num_pieces)])
        
        # Counting how rare pieces are
        piece_availability = [0] * num_pieces
        for peer in peers:
            for piece in peer.available_pieces:
                piece_availability[piece] += 1

        rarity_key = lambda pid: piece_availability[pid]

        # Divide pieces by their rarity
        pieces_by_rarity = [set() for _ in range(len(peers) + 1)]
        for needed_piece in needed_pieces_list:
            pieces_by_rarity[rarity_key(needed_piece)].add(needed_piece)

        # for i, pieces_in_rarity_group in enumerate(pieces_by_rarity):
        #    print("Rarity group %d: %s\n"%(i, str(pieces_in_rarity_group)))

        # Create Requests
        requests = []

        for peer in peers:
            av_set = set(peer.available_pieces)
            remaining_requests = self.max_requests

            # ASSUMPTION that between equally rare pieces, we randomly choose which ones to request from a given peer
            for pieces_in_rarity_group in pieces_by_rarity:
                isect = av_set.intersection(pieces_in_rarity_group)
                n = min(remaining_requests, len(isect))

                for piece_id in random.sample(isect, n):
                    start_block = self.pieces[piece_id]
                    r = Request(self.id, peer.id, piece_id, start_block)
                    requests.append(r)

                remaining_requests -= n

        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """

        # ASSUMPTION that between matching download rates from peers, we break ties randomly (also means we initialize randomly)
        # ASSUMPTION that if some unchoke slots are not taken (maybe lack of requests or a previous peer is no longer requesting),
        # we continue to try to fill them based on the latest histories, even if the round is not a multiple of 10, leaving the slots
        # that are already filled with the same peers

        round = history.current_round()

        # Do some preprocessing of incoming requests
        amount_requested = defaultdict(lambda: 0)
        peers_requesting = set()
        for request in requests:
            peers_requesting.add(request.requester_id)
            amount_requested[request.requester_id] += self.conf.blocks_per_piece - request.start


        # If a peer is no longer requesting, free the slot
        self.regular_slots = self.regular_slots.intersection(peers_requesting)
        self.optimistic_unchoke = self.optimistic_unchoke.intersection(peers_requesting)
        unchoked_set = self.regular_slots.union(self.optimistic_unchoke)
        choked_set = peers_requesting.difference(unchoked_set)

        # Figure out who to unchoke
        if (round % 10 == 0) or len(unchoked_set) < self.num_slots:
            # Calculate total amount downloaded from peers from last 20 rounds

            # The random initialization is a trick to break ties between same average/cumulative downloads
            download_total = defaultdict(lambda: random.uniform(0, 1))

            for rounds_past in range(1, min(round, 21)): # 21 to make the total number of rounds added up equal 20
                for download in history.downloads[round - 1]:
                    if download.to_id == self.id: # Probably unnecessary check but just in case
                        download_total[download.from_id] += download.blocks

            # Completely restart the decision on these key rounds
            if round % 10 == 0:
                self.regular_slots = set()
            if round % 30 == 0:
                self.optimistic_unchoke = set()
            
            best_peers = sorted(list(choked_set), key=lambda peer: download_total[peer], reverse=True)

            # unchoke up to num_slots - 1 regularly
            num_regular_unchoke = min(len(best_peers), self.num_slots - 1 - len(self.regular_slots))
            self.regular_slots.update(best_peers[:num_regular_unchoke])

            # optimistic unchoke is applicable
            if len(self.optimistic_unchoke) == 0 and num_regular_unchoke < len(best_peers):
                self.optimistic_unchoke.add(random.choice(best_peers[num_regular_unchoke:]))

        # ASSUMPTION that if some peers request less than the amount they would have been given, the
        # excess is given to the other peers. If all peers have their requests completely satisfied, we
        # do not use the excess bandwidth

        # ASSUMPTION that if unable to split evenly because it does not divide, we arbitrarily choose some
        # to give 1 more block to
        unchoked_list = list(self.regular_slots) + list(self.optimistic_unchoke)
        unchoked_list.sort(key=lambda peer: amount_requested[peer])

        uploads = []
        remaining_bw = self.up_bw
        for i, peer in enumerate(unchoked_list):
            # check to see if this peer will be maxed out
            if amount_requested[peer] * (len(unchoked_list) - i) < remaining_bw:
                amt_upload = amount_requested[peer]
                remaining_bw -= amount_requested[peer]
            else:
                amt_upload = remaining_bw // (len(unchoked_list) - i)

            uploads.append(Upload(self.id, peer, amt_upload))
            remaining_bw -= amt_upload

        return uploads

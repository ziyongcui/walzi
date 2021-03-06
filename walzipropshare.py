#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging
import math
from collections import defaultdict

from messages import Upload, Request
from util import even_split
from peer import Peer

class WalziPropShare(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"

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

        round = history.current_round()

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.
        chosen = []
        bws = []

        total_blocks = 0

        requesters = set()
        for request in requests:
            requesters.add(request.requester_id)
        received_from = defaultdict(lambda: 0)

        random_selection_set = set()

        ## look at history.downloads[round-1] and find the total number of uploads
        last_round_downloads = history.downloads[round - 1] if round > 0 else []
        for requester in requesters:
            ## we only upload the peers who request from us
            for peer_tuple in last_round_downloads:
                if peer_tuple.from_id == requester:
                    total_blocks += peer_tuple.blocks
                    received_from[requester] += peer_tuple.blocks

            if received_from[requester] == 0:
                random_selection_set.add(requester)

        share = defaultdict(lambda: 0)
        if total_blocks == 0:
            for requester in requesters:
                share[requester] = self.up_bw / len(requesters)
        else:
            regular_allocation = 0.9

            if len(random_selection_set) == 0:
                regular_allocation = 1
            else:
                share[random.choice(list(random_selection_set))] = self.up_bw * (1 - regular_allocation)

            for requester in requesters:
                share[requester] = received_from[requester] / total_blocks * regular_allocation * self.up_bw

        uploads = []

        remaining_roundups = self.up_bw
        for requester in requesters:
            remaining_roundups -= int(share[requester])
        requesters = sorted(list(requesters), key=lambda requester: share[requester] % 1, reverse=True)
        for requester in requesters:
            amt = int(share[requester])
            if remaining_roundups > 0:
                amt += 1
                remaining_roundups -= 1
            uploads.append(Upload(self.id, requester, amt))

        return uploads

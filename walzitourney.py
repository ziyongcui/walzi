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

class WalziTourney(Peer):
    def post_init(self):
        self.regular_slots = set()
        self.optimistic_unchoke = set()

        self.num_slots = min(4, self.up_bw) # ASSUMPTION that we set the number of unchoke slots to 4 or less if we can't even provide that much uploading
        self.period = 10
        self.r = 3 # Number of periods between optimisitc unchokes

        min_up_bw = self.conf.min_up_bw
        max_up_bw = self.conf.max_up_bw
        expected_bw = (min_up_bw + max_up_bw) / 2
        init_alpha_estimate = expected_bw / 4 # Assuming evenly divided among 4 slots

        self.reputation = defaultdict(lambda: init_alpha_estimate)

        self.sum = defaultdict(lambda: 0)
        self.n = defaultdict(lambda: 0)
        # Number of pieces we want before resorting to rarity algorithm. Before this point we just try to get to this many pieces ASAP
        self.threshold_pieces = 5 #len(self.pieces) / 6



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
        needed_pieces_list = list(filter(needed, [x for x in range(num_pieces)]))
        num_pieces_have = num_pieces - len(needed_pieces_list)

        requests = []
        
        if False: #num_pieces_have < self.threshold_pieces:
            random.shuffle(needed_pieces_list)
            needed_pieces_list.sort(key=lambda x: self.pieces[x], reverse=True)

            for peer in peers:
                remaining_requests = self.max_requests
                peer_requests = []
                for piece in needed_pieces_list:
                    if piece in peer.available_pieces and remaining_requests > 0:
                        start_block = self.pieces[piece]
                        r = Request(self.id, peer.id, piece, start_block)
                        peer_requests.append(r)
                        remaining_requests -= 1
                random.shuffle(peer_requests)
                requests.extend(peer_requests)
        else:
            
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

        num_pieces = len(self.pieces)

        needed = lambda pid: self.pieces[pid] < self.conf.blocks_per_piece
        needed_pieces_list = list(filter(needed, [x for x in range(num_pieces)]))

        # Evil after we have what we want
        if len(needed_pieces_list) == 0:
            return []

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

        current_received_from = defaultdict(lambda: 0)
        if round - 1 > 0:
            for download in history.downloads[round - 1]:
                current_received_from[download.from_id] += download.blocks

        random_selection_set = set()

        for peer in current_received_from.keys():
            if current_received_from[peer] > 0:
                self.n[peer] += 1
                self.sum[peer] += current_received_from[peer]
                self.reputation[peer] = self.sum[peer]/self.n[peer]
                # print("REP is: " + str(self.reputation[peer]) + " for " + str(peer))
        ## look at history.downloads[round-1] and find the total number of uploads
        last_round_downloads_1 = history.downloads[round - 1] if round > 0 else []
        last_round_downloads_2 = history.downloads[round - 2] if round > 1 else []
        last_round_downloads_3 = history.downloads[round - 3] if round > 2 else []

        
        for requester in requesters:
            ## we only upload the peers who request from us
            for peer_tuple in last_round_downloads_1:
                if peer_tuple.from_id == requester:
                    total_blocks += 3 * peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10
                    received_from[requester] += 3 * peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10
            for peer_tuple in last_round_downloads_2:
                if peer_tuple.from_id == requester:
                    total_blocks += 2 * peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10
                    received_from[requester] += 2 * peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10
            for peer_tuple in last_round_downloads_3:
                if peer_tuple.from_id == requester:
                    total_blocks += peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10
                    received_from[requester] += peer_tuple.blocks * self.reputation[peer_tuple.from_id] / 10

            if received_from[requester] == 0:
                random_selection_set.add(requester)

        share = defaultdict(lambda: 0)
        if total_blocks == 0:
            for requester in requesters:
                share[requester] = self.up_bw / len(requesters)
        else:
            regular_allocation = 0.8

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


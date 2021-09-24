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

class WalziTyrant(Peer):
    def post_init(self):
        self.r = 1
        self.gamma = 0.1
        self.alpha = 0.2
        self.period = 5
        self.debug = False

        min_up_bw = self.conf.min_up_bw
        max_up_bw = self.conf.max_up_bw

        # Use the expected bandwidth
        expected_bw = (min_up_bw + max_up_bw) / 2
        init_d_estimate = expected_bw / 4 # Assuming evenly divided among 4 slots
        init_u_estimate = self.up_bw / 4 # Arbitrary assumption so that we unchoke 4 at the start

        # The estimates stored as dicts
        self.d = defaultdict(lambda: init_d_estimate)
        self.u = defaultdict(lambda: init_u_estimate)
        self.unchoked = set()
        self.time_unchoked_by = defaultdict(lambda: 0)

        if self.debug:
            print("Config: %s"%self.conf)
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
        peer_set = set([peer.id for peer in peers])

        # Record how much received from each peer
        received_from = defaultdict(lambda: 0)

        if round - 1 > 0:
            for download in history.downloads[round - 1]:
                received_from[download.from_id] += download.blocks
            # print("Received %d from %s"%(download.blocks, download.from_id))

        for peer in received_from.keys():
            if received_from[peer] > 0:
                self.d[peer] = received_from[peer]

        if self.debug:
            print("Received: %s"%received_from)

        # Update estimations (going off of end from last period)

        if round % self.period == 0:
            # Keep track of how long we have been unchoked by our peers
            for peer in peer_set.difference(set(received_from.keys())):
                self.time_unchoked_by[peer] = 0
            for peer in received_from.keys():
                self.time_unchoked_by[peer] += 1

            for peer in self.unchoked:
                if received_from[peer] > 0:
                    if self.time_unchoked_by[peer] >= self.r:
                        self.u[peer] *= 1 - self.gamma
                else:
                    self.u[peer] *= 1 + self.alpha

                    # Benefit of having this line is to make sure the random pertubations don't break the order
                    self.u[peer] = min(self.u[peer], self.conf.max_up_bw)

            random_pertubation_max = 1 / (self.conf.max_up_bw * self.conf.max_up_bw)
            self.efficiency_map = dict()
            
            if self.debug:
                print("Efficiencies:")
            for peer in peers:
                # We make the denominator an integer because that is what we'll actually be sending them
                self.efficiency_map[peer.id] = self.d[peer.id] / max(1, int(self.u[peer.id])) + random.uniform(0, random_pertubation_max)
                if self.debug:
                    print("From %s: %d / %d = %f"%(peer.id, self.d[peer.id], max(1, int(self.u[peer.id])), self.d[peer.id] / max(1, int(self.u[peer.id]))))
            
            if self.debug:
                print("Time Unchoked:")
                for peer in peers:
                   print("By %s: %d"%(peer.id, self.time_unchoked_by[peer.id]))

        requesters = set()
        for request in requests:
            requesters.add(request.requester_id)
        
        if self.debug:
            print("Requesters: %s"%(requesters))

        # self.unchoked = self.unchoked.intersection(requesters)
        if round % self.period == 0:
            self.unchoked.clear()

        choked_requesters = requesters.difference(self.unchoked)
        sorted_requesters = sorted(list(choked_requesters), key=lambda peer: self.efficiency_map[peer], reverse=True)
            
        uploads = []
        remaining_bw = self.up_bw

        for requester in set(self.unchoked).intersection(requesters):
            bw = int(self.u[requester])
            if remaining_bw >= bw:
                uploads.append(Upload(self.id, requester, bw))
                remaining_bw -= bw

        if round % self.period == 0:
            for requester in sorted_requesters:
                bw = int(self.u[requester])
                if remaining_bw >= bw:
                    uploads.append(Upload(self.id, requester, bw))
                    remaining_bw -= bw
                    self.unchoked.add(requester)
                else:
                    break
        
        if self.debug:
            print("Unchoking: %s"%(self.unchoked))

        return uploads

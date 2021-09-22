#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class WalziTourney(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"

    ## use rareest first
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

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.

        download_estimates = dict()

        if round > 0:
            for i in range(0,round):
                print("HERE", self.id)
                for peer_tuple in history.downloads[i]:
                    print(peer_tuple, "Round " + str(i))
        #     for peer_tuple in history.downloads[round - 1]:
        #         print(peer_tuple)
        #         if peer_tuple.from_id in download_estimates:
        #             download_estimates[peer_tuple.from_id] += peer_tuple.blocks
        #         else:
        #             download_estimates[peer_tuple.from_id] = peer_tuple.blocks
        # print(download_estimates)

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
        else:
            logging.debug("Still here: uploading to a random peer")
            # change my internal state for no reason
            self.dummy_state["cake"] = "pie"

            request = random.choice(requests)
            chosen = [request.requester_id]
            # Evenly "split" my upload bandwidth among the one chosen requester
            bws = even_split(self.up_bw, len(chosen))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads

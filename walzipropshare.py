#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging
import math

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
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = list(filter(needed, list(range(len(self.pieces)))))
        np_set = set(needed_pieces)  # sets support fast intersection ops.


        logging.debug("%s here: still need pieces %s" % (
            self.id, needed_pieces))

        logging.debug("%s still here. Here are some peers:" % self.id)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" % (p.id, p.available_pieces))

        logging.debug("And look, I have my entire history available too:")
        logging.debug("look at the AgentHistory class in history.py for details")
        logging.debug(str(history))

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)

        # Sort peers by id.  This is probably not a useful sort, but other
        # sorts might be useful
        peers.sort(key=lambda p: p.id)
        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n = min(self.max_requests, len(isect))
            # More symmetry breaking -- ask for random pieces.
            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.
            for piece_id in random.sample(isect, n):
                # aha! The peer has this piece! Request it.
                # which part of the piece do we need next?
                # (must get the next-needed blocks in order)
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

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
        chosen = []
        bws = []
        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
        else:
            # logging.debug("Still here: uploading to a random peer")
            # change my internal state for no reason
            self.dummy_state["cake"] = "pie"

            if round == 0:
                ## we try to allocate
                for request in requests:
                    chosen.append(request.requester_id)
                    bws = even_split(self.up_bw, len(chosen))
            else:
                total_blocks = 0
                total_percent = 0.9
                imp_peers = []
                total_peers = []
                for peer in peers:
                    if peer.id[:4] != "Seed":
                        total_peers.append(peer.id)

                requester_id = []
                for request in requests:
                    requester_id.append(request.requester_id)
                ## look at history.downloads[round-1] and find the total number of uploads
                for request in requests:
                    ## we only upload the peers who request from us
                    for peer_tuple in history.downloads[round-1]:
                        if (peer_tuple.from_id == request.requester_id and peer_tuple.blocks > 0):
                            total_blocks += peer_tuple.blocks
                            imp_peers.append((peer_tuple.from_id, peer_tuple.blocks))
                ## this should give the peers who are requesting from us and have uploaded to us in the past
                not_reserved = int(math.ceil(self.up_bw * total_percent))
                reserved = int(self.up_bw - not_reserved)

                for peer in imp_peers:
                    chosen.append(peer[0])
                    rate = (peer[1] / total_blocks)
                    bws.append(int(math.floor(rate * not_reserved)))

                count = 0
                if len(bws) > 0:
                    while not_reserved > sum(bws):
                        try:
                            bws[count] += 1
                            count += 1
                        except:
                            count = 0
                else:
                    reserved = self.up_bw

                not_peer = [item for item in total_peers if item not in imp_peers]
                optimistic = random.choice(not_peer)
                chosen.append(optimistic)
                bws.append(reserved)
                # print(self.id, chosen, bws, "HIIIIIIIIIIII", reserved)





            # request = random.choice(requests)
            # chosen = [request.requester_id]
            # Evenly "split" my upload bandwidth among the one chosen requester


        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads

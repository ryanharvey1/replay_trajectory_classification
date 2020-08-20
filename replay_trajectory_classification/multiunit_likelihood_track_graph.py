import copy

import dask.bag as db
import networkx as nx
import numpy as np


def _distance_to_bin_centers(left_node, right_node, distance_left_node,
                             distance_right_node, time_ind, copy_graph,
                             place_bin_center_node_ids):
    node_name = f"actual_position_{time_ind}"
    copy_graph.add_node(node_name)
    copy_graph.add_edge(
        left_node, node_name, distance=distance_left_node)
    copy_graph.add_edge(
        node_name, right_node, distance=distance_right_node)
    distance_to_bin_centers = [
        nx.shortest_path_length(
            copy_graph, source=bin_center, target=node_name,
            weight="distance")
        for bin_center in place_bin_center_node_ids]
    copy_graph.remove_node(node_name)

    return distance_to_bin_centers


def find_adjacent_nodes(nodes_df, linear_position):
    # Find the index of the nodes to insert between
    right_bin_ind = np.searchsorted(
        nodes_df.linear_position.values, linear_position, side="right")
    left_bin_ind = right_bin_ind - 1

    # Fix for ones that fall into invalid track positions
    # Note: Need to test on different binnings
    # Another solution is to find the edge this falls on directly.
    not_same_edge = (nodes_df.edge_id.values[left_bin_ind] !=
                     nodes_df.edge_id.values[right_bin_ind])
    right_bin_ind[not_same_edge] = right_bin_ind[not_same_edge] - 1
    left_bin_ind[not_same_edge] = left_bin_ind[not_same_edge] - 1

    # Get adjacent node names and distance
    left_node = nodes_df.reset_index().node_ids.values[left_bin_ind]
    right_node = nodes_df.reset_index().node_ids.values[right_bin_ind]

    distance_left_node = np.abs(
        nodes_df.loc[left_node].linear_position.values - linear_position)
    distance_right_node = np.abs(
        nodes_df.loc[right_node].linear_position.values - linear_position)

    return left_node, right_node, distance_left_node, distance_right_node


def get_distance_to_bin_centers(linear_position, decoder, npartitions=100):
    copy_graph = copy.deepcopy(decoder.track_graph_)
    linear_position = linear_position.squeeze()
    nodes_df = decoder._nodes_df.set_index("node_ids")
    place_bin_center_node_ids = (
        nodes_df
        .loc[~nodes_df.is_bin_edge]
        .reset_index()
        .node_ids
        .values)
    (left_node, right_node, distance_left_node,
     distance_right_node) = find_adjacent_nodes(nodes_df, linear_position)

    left_node = db.from_sequence(
        left_node, npartitions=npartitions)
    right_node = db.from_sequence(
        right_node, npartitions=npartitions)
    distance_left_node = db.from_sequence(
        distance_left_node, npartitions=npartitions)
    distance_right_node = db.from_sequence(
        distance_right_node, npartitions=npartitions)
    time_ind = db.from_sequence(
        range(linear_position.shape[0]), npartitions=npartitions)

    return np.asarray(left_node.map(
        _distance_to_bin_centers, right_node, distance_left_node,
        distance_right_node, time_ind, copy_graph,
        place_bin_center_node_ids).compute())


def gaussian_kernel(distance, bandwidth):
    return (np.exp(-0.5 * (distance / bandwidth)**2) /
            (bandwidth * np.sqrt(2.0 * np.pi))) / bandwidth

import networkx as nx
from pyvis.network import Network
import numpy as np
import os
import re
import traceback


class VimwikiGraph:

    # {{{ Private
    def __init__(self, root_dir: str, file_extensions: list = ['md'], graph_name: str = 'vimwikigraph', **args):
        self.graph = nx.DiGraph(name=graph_name)
        self.root_dir = root_dir
        self.file_extensions = file_extensions
        self.lines = dict()
        node_dict = self.__create_nodes()
        self.__parse_and_add_edges(node_dict)

    def __normalize_path(self, root, link):
        if re.match(r'https?://', link):
            link = re.sub(r'.*:/+', '', link)
            link = re.sub(r'/.*', '', link)
            return link
        if re.match('file:', link):
            link = re.sub(r'.*:', '', link)
            return link
        link = re.sub(r'.*/', '', link)
        if len(root) > 0:
            return os.path.join(root, link)
        return link

    def __resolve_relative_path(self, path):
        if path[0] == '/':
            return path
        return os.path.join(self.root_dir, path)

    def __add_suffix_to_node(self, path):
        if not path.endswith(".md"):
            return path + ".md"

    def __create_nodes(self):
        node_dict = dict()
        for root, dir, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith('.md'):
                    name = file.removesuffix('.md')
                    node_dict[name] = root
                    self.graph.add_node(name, label=name)
        return node_dict

    def __parse_and_add_edges(self, node_dict):
        for name, root in node_dict.items():
            with open(os.path.join(root, name) + '.md', 'r') as f:
                lines = f.readlines()

            name = re.sub(r'.*/', '', name)
            name = name.removesuffix('.md')

            self.lines[name] = lines

            for line in lines:
                links = re.findall(r'\[[^\]]*\]\(([^\)]+)\)', line)
                for link in links:
                    link = link.removesuffix('.md')

                    child_node = self.__normalize_path('', link)
                    self.graph.add_edge(name, child_node)

                    root_file_path = os.path.join(self.root_dir, link + '.md')
                    diary_file_path = os.path.join(self.root_dir, 'diary', link + '.md')
                    if not os.path.exists(root_file_path) \
                            and not os.path.exists(diary_file_path):
                        self.graph.nodes[child_node]['color'] = 'grey'

                    if child_node == 'diary' or re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', child_node):
                        self.graph.nodes[child_node]['color'] = 'green'

                tags = re.findall(r'(\s|^)(@[a-z0-9_-]+\b)', line)
                for tag in tags:
                    tag = tag[1]
                    self.graph.add_edge(name, tag)
                    self.graph.nodes[tag]['color'] = 'orange'


    def __filter_lines(self, regexes: list, lines):
        """
        Returns true if all of the provided regexes match.

        Args:
            regexes (list): List of regular expressions.
            lines (list): List of lines to match.
        """
        match_count = len(regexes)
        matches = 0
        try:
            for regex in regexes:
                for line in lines:
                    if re.search(regex, line.lower()):
                        matches += 1
                        break
                if matches == match_count:
                    return True
        except Exception as e:
            print(e)
        return False
    # }}}

    # {{{ Output
    def write(self, name: str = None, filetype: str = 'png'):
        """
        Writes the current graph to one of name.png or name.dot

        Args:
            name (str): Name of the resulting file.
            filetype (str): File type. May be either 'png' or 'dot'.
        """
        if not name:
            name = self.graph.name
        PG = nx.drawing.nx_pydot.to_pydot(self.graph)
        PG.set_rankdir('LR')
        if filetype == 'png':
            PG.write_png(f"{name}.png")
        elif filetype == 'dot':
            PG.write_raw(f"{name}.dot")
        elif filetype == 'gml':
            nx.write_gml(self.graph, f"{name}.gml")
        else:
            raise Exception("Invalid file type")

    def write_pyviz(self, name: str = None):
        if not name:
            name = self.graph.name
        nt = Network(
            height='80vh',
            width='95vw',
            neighborhood_highlight=True,
            filter_menu=True,
            cdn_resources='remote',
        )
        nt.from_nx(self.graph)
        with open(f'{name}.html', 'w') as f:
            f.write(nt.generate_html())
    # }}}

    # {{{ Graph Operations
    def add_attribute_by_regex(self, regexes: list, attribute: list, value: list):
        """
        Add attributes with the corresponding values to documents whose contents is matched by a
        conjunction of the specified regexes.

        Args:
            regexes (list)
            attribute (list): list of graphviz attribute names
            value (list): list of corresponding values
        """
        for node in self.graph.nodes:
            lines = self.lines.get(node, list())
            if self.__filter_lines(regexes, lines):
                for attr, val in zip(attribute, value):
                    self.graph.nodes[node][attr] = val
        return self

    def weight_attribute(self, attribute: str = 'fontsize', min_val: int = 20, max_val: int = 100):
        """
        Adds and scales a DOC attribute according to a node's scaled betweenness centrality.
        It will assign the maximum value to the node with the highest betweenness centrality.

        Args:
            attribute: The attribute to add and scale.
            min_val: Minimum value.
            max_val: Maximum value.
        """
        try:
            exponent = np.log(max_val)/np.log(min_val)
            centrality = nx.betweenness_centrality(self.graph)
            max_centrality = max(centrality.values())
            if not max_centrality:
                return self
            for key, value in centrality.items():
                val = max(min((min_val*value/max_centrality)**exponent, max_val), min_val)
                self.graph.nodes[key][attribute] = val
        except Exception as e:
            print(e)
        finally:
            return self

    def filter_nodes(self, regexes: list):
        """
        Filters nodes by regexes. All nodes that do not match one of the regular expressions in
        'regexes' will be removed.

        Args:
            regexes (list)
        """
        nodes_to_remove = list()
        for node in self.graph.nodes:
            remove_node = True
            lines = self.lines.get(node, list())
            if self.__filter_lines(regexes, lines):
                remove_node = False
            if remove_node:
                nodes_to_remove.append(node)
        self.graph.remove_nodes_from(nodes_to_remove)
        return self

    def collapse_children(self, node: str, depth: int = 1):
        """
        All child nodes will be collapsed into this node. Edges from and to children
        will go to the parent instead.

        Args:
            node (str): Full or relative path of a vimwiki document.
            depth (int): Number of levels to contract. Setting depth to a high value
                will remove all of the node's children
        """
        try:
            node = self.__resolve_relative_path(node)
            node = self.__add_suffix_to_node(node)
            children = nx.dfs_successors(self.graph, node, depth)
            for child in np.concatenate(list(children.values())):
                nx.contracted_nodes(self.graph, node, child, self_loops=False, copy=False)
            del self.graph.nodes[node]['contraction']
        except Exception:
            traceback.print_exc()
        finally:
            return self

    def remove_nonadjacent_nodes(self, node: str, depth: int = 1):
        """
        Removes all nodes that are not successors (up to a certain depth)
        of the specified node in an undirected copy of the graph.

        Args:
            node (str)
            depth (int)
        """
        node = self.__resolve_relative_path(node)
        adjacent_nodes = [node]
        successors = nx.dfs_successors(self.graph.to_undirected(), node, depth)
        if len(list(successors.values())):
            adjacent_nodes.extend(np.concatenate(list(successors.values())))
        adjacent_nodes = np.unique(adjacent_nodes)
        nodes_to_remove = list()
        for n in self.graph.nodes:
            if n not in adjacent_nodes:
                nodes_to_remove.append(n)
        self.graph.remove_nodes_from(nodes_to_remove)
        self.graph.nodes[node]['color'] = 'red'
        self.graph.nodes[node]['style'] = 'filled'
        return self

    def extend_node_label(self, regexes: list, join_str: str = '\n'):
        """
        Add additional information to node labels.

        Args:
            regexes (list): list of regexes to match data in the node's corresponding documents
            join_str (str): a string or character used to join any matches
        """
        try:
            for node in self.graph.nodes:
                lines = self.lines[node]
                all_matches = list()
                for regex in regexes:
                    for line in lines:
                        matches = re.findall(regex, line)
                        all_matches.extend(matches)
                label = self.graph.nodes[node]['label']
                label = f'"{label}{join_str}{join_str.join(all_matches)}"'
                self.graph.nodes[node]['label'] = label
        except Exception as e:
            print(e)
        finally:
            return self
# }}}

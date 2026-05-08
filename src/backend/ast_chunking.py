from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_java as tsjava
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo
import tree_sitter_rust as tsrust
import tree_sitter_ruby as tsruby
import tree_sitter_c_sharp as tscsharp
from pathlib import Path
from typing import Dict

MAX_CHUNKS = 3000

NAME_TYPES = {"identifier", "type_identifier", "property_identifier",
                  "constant", "name", "field_identifier"}

#Extension Mapping
EXTENSION_MAP ={
    ".py": ("python", lambda: Language(tspython.language())),
    ".js": ("javascript", lambda: Language(tsjavascript.language())),
    ".mjs": ("javascript", lambda: Language(tsjavascript.language())),
    ".ts": ("typescript", lambda: Language(tstypescript.language_typescript())),
    ".tsx": ("typescript", lambda: Language(tstypescript.language_typescript())),
    ".java": ("java", lambda: Language(tsjava.language())),
    ".c": ("c", lambda: Language(tscpp.language())),
    ".cpp": ("c", lambda: Language(tscpp.language())),
    ".cc": ("c", lambda: Language(tscpp.language())),
    ".h": ("c", lambda: Language(tscpp.language())),
    ".hpp": ("c", lambda: Language(tscpp.language())),
    ".go": ("go", lambda: Language(tsgo.language())),
    ".rs": ("rust", lambda: Language(tsrust.language())),
    ".rb": ("ruby", lambda: Language(tsruby.language())),
    ".cs": ("c_sharp", lambda: Language(tscsharp.language()))
}


#Node Schema
LANG_SCHEMA = {
    "python" : {
        'top_level': {'function_definition', 'class_definition'},
        'class_like': {'class_definition'},
        'method_like': {'function_definition'},
        'body_node': 'block',
        'wrapper_nodes': {'decorated_definition'}
    },
    'javascript': {
        'top_level': {'function_definition', 'class_declaration',
                      'lexical_declaration', 'variable_declaration'},
        'class_like': {'class_declaration'},
        'method_like': {'method_definition', 'field_definition'},
        'body_node': 'class_body',
        'wrapper_nodes': set()
    },
    'typescript': {
        'top_level': {'function_definition', 'class_declaration',
                      'interface_declaration', 'type_alias_declaration', 'abstract_class_declaration'},
        'class_like': {'class_declaration','interface_declaration', 'abstract_class_declaration'},
        'method_like': {'method_definition','method_signature',
                        'abstract_method_signature', 'field_definition', 'public_field_definition'},
        'body_node': 'class_body',
        'wrapper_nodes': {'ambient_declaration'}
    },
    'java': {
        'top_level': {'class_declaration', 'interface_declaration', 'enum_declaration'},
        'class_like': {'class_declaration','interface_declaration', 'enum_declaration'},
        'method_like': {'method_declaration', 'constructor_declaration', 'static_initializer'},
        'body_node': 'class_body',
        'wrapper_nodes': set()
    },
    'c': {
        'top_level': {'function_definition', 'declaration', 'preproc_function_def'},
        'class_like': set(), #C has no class
        'method_like': set(),
        'body_node': None,
        'wrapper_nodes': set()
    },
    'cpp': {
        'top_level': {'function_definition', 'class_specifier',
                      'struct_specifier', 'template_declaration'},
        'class_like': {'class_specifier','struct_specifier'},
        'method_like': {'function_definition'},
        'body_node': 'field_declaration_list',
        'wrapper_nodes': set()

    },
    'go': {
        "top_level": {'function_declaration','method_declaration','type_declaration'},
        'class_like': set(),
        'method_like': set(),
        'body_node': None,
        'wrapper_nodes': set()
    },
    'rust': {
        'top_level': {'function_item', 'struct_item','enum_item',
                      'impl_item', 'trait_item'},
        'class_like': {'impl_item','trait_item'},
        'method_like': {'function_item', 'const_item', 'type_item','macro_invocation'},
        'body_node': 'declaration_list',
        'wrapper_nodes': set()
    },
    "ruby": {
        "top_level":   {"method", "class", "module"},
        "class_like":  {"class", "module"},
        "method_like": {"method", "singleton_method", 'call'},
        "body_node":   "body_statement",
        'wrapper_nodes': {'visibility_modifier'}
    },
    'c_sharp': {
        'top_level': {'class_declaration', 'interface_declaration',
                      'struct_declaration', 'namespace_declaration', 'record_declaration'},
        'class_like': {'class_declaration', 'interface_declaration',
                      'struct_declaration', 'namespace_declaration', 'record_declaration'},
        'method_like': {'method_declaration', 'constructor_declaration',
                        'property_declaration', 'indexer_declaration', 'operator_declaration',
                        'event_field_declaration','destructor_declaration'},
        'body_node': 'declaration_list',
        'wrapper_nodes': set()
    }
}


#Fetching teh parser based on the extension of the file
_parser_cache: Dict[str, Parser] = {}

def get_parser(ext: str):
    entry = EXTENSION_MAP.get(ext.lower())
    if not entry:
        return None, None
    lang_name, lang_factory = entry
    if lang_name not in _parser_cache:
        _parser_cache[lang_name] = Parser(lang_factory())
    return lang_name, _parser_cache[lang_name]

#Extracting the name of the child of the node
def extract_node_name(node) -> str:
    """
    Walking a node's children to find the name/identifier.
    """
    for child in node.children:
        if child.type in NAME_TYPES:
            return child.text.decode('utf8')
    return 'unknown'

#extracting header of the class
def extract_class_header(content: str, class_node, body_node_type: str) -> str:
    """
    Slice everything before the body block - give just the class signature
    """
    for child in class_node.children:
        if child.type == body_node_type:
            return content[class_node.start_byte: child.start_byte].strip()
    #Fallback: first line only
    return content[class_node.start_byte:class_node.end_byte].split('\n')[0]

def get_methods_from_class(class_node, body_node_type: str,
                           method_types: set, wrapper_nodes: set) -> list:
    methods = []
    for child in class_node.children:
        if child.type != body_node_type:
            continue

        for item in child.children:
            if item.type in method_types:
                methods.append(item)
            elif item.type in wrapper_nodes:
                for sub in item.children:
                    if sub.type in method_types:
                        methods.append(sub)
    return methods

#Method chunker
def chunk_large_class(file: dict, class_node, class_name: str,
                      schema: dict, lang_name: str) -> list[dict]:
    """
    Recursively split a large class/impl/module into per-method chunks.
    Each chunk is prefixed with the class header for context.
    """

    body_node_type = schema['body_node']
    method_types = schema['method_like']
    class_types = schema['class_like']

    class_header = extract_class_header(file['content'], class_node, body_node_type)
    chunks=[]

    def walk_body(parent_node, parent_name: str):
        for child in parent_node.children:
            if child.type == body_node_type:
                # Stepping into the body
                walk_body(child, parent_name)

            elif child.type in method_types:
                method_name = extract_node_name(child)
                method_text = file['content'][child.start_byte:child.end_byte]
                full_name = f"{parent_name}.{method_name}"

                chunks.append({
                    'id': f"{file['repo']}::{file['path']}::{full_name}",
                    'text': f"{class_name}\n ...\n{method_text}",
                    'type': 'method',
                    'name': full_name,
                    'file_path': file['path'],
                    'language': lang_name,
                    'start_line': child.start_point[0],
                    'end_line': child.end_point[0],
                    'repo': file['repo']
                })

            elif child.type in class_types:
                nested_name= extract_node_name(child),
                nested_text= file['content'][child.start_byte:child.end_byte]

                if len(nested_text) <= MAX_CHUNKS:
                    chunks.append(_make_chunk(file, child, "class",lang_name))
                else:
                    walk_body(child, f"{parent_name}.{nested_name}")

    walk_body(class_node, class_name)
    return chunks

def _make_chunk(file: dict, node, chunk_type: str, lang_name:str)-> dict:
    name = extract_node_name(node)
    return{
        'id': f"{file['repo']}::{file['path']}::{name}",
        'text': file['content'][node.start_byte:node.end_byte],
        'type': chunk_type,
        'name': name,
        'file_path': file['path'],
        'language': lang_name,
        'start_line': node.start_point[0],
        'end_line': node.end_point[0],
        'repo': file['repo']
    }

def _method_chunk(file: dict, method_node, class_name: str,
                  class_header: str, lang_name: str):
    method_name = extract_node_name(method_node)
    full_name= f"{class_name}.{method_name}"
    method_text = file['content'][method_node.start_byte:method_node.end_byte]
    return {
        "id": f"{file['repo']}::{file['path']}::{full_name}",
        "text": f"{class_header}\n    ...\n{method_text}",
        "type": "method",
        "name": full_name,
        "file_path": file["path"],
        "language": lang_name,
        "start_line": method_node.start_point[0],
        "end_line": method_node.end_point[0],
        "repo": file["repo"],
    }

def _whole_file_chunk(file: dict, lang_name: str) -> dict:
    return {
        'id': f"{file['repo']}::{file['path']}::_file",
        'text': file['content'],
        'type': 'file',
        'name': file['path'],
        'file_path': file['path'],
        'language': lang_name,
        'start_line': 0,
        'end_line': file["content"].count("\n"),
        'repo': file['repo']
    }

def chunk_code_file(file: dict):
    """
    Auto-detect the language, parse teh file and return the semantic chunks.
    Large classes are automatically split into per method chunks
    """

    ext = Path(file['path']).suffix
    lang_name, parser = get_parser(ext)

    if parser is None:
        return[_whole_file_chunk(file, "unknown")]

    schema = LANG_SCHEMA[lang_name]
    tree = parser.parse(bytes(file['content'], 'utf8'))
    chunks = []

    for node in tree.root_node.children:
        if node.type not in schema['top_level']:
            continue

        chunk_text = file['content'][node.start_byte:node.end_byte]
        is_class = node.type in schema['class_like']

        if is_class and len(chunk_text) > MAX_CHUNKS and schema['body_node']:
            class_name = extract_node_name(node)
            class_header = extract_class_header(file['content'], node, schema['body_node'])

            methods = get_methods_from_class(node, schema['body_node'],
                                             schema['method_like'], schema['wrapper_nodes'])

            if methods:
                for m in methods:
                    chunks.append(_method_chunk(file, m, class_name, class_header, lang_name))
            else:
                chunks.append(_make_chunk(file, node, chunk_type, lang_name))

        else:
            chunk_type = 'class' if is_class else 'function'
            chunks.append(_make_chunk(file, node, chunk_type, lang_name))

    if not chunks:
        chunks.append(_whole_file_chunk(file, lang_name))

    return chunks


























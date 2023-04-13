# The sample script and documentation are provided AS IS and are not supported by
# the author or the author's employer, unless otherwise agreed in writing. You bear
# all risk relating to the use or performance of the sample script and documentation.
# The author and the author's employer disclaim all express or implied warranties
# (including, without limitation, any warranties of merchantability, title, infringement
# or fitness for a particular purpose). In no event shall the author, the author's employer
# or anyone else involved in the creation, production, or delivery of the scripts be liable
# for any damages whatsoever arising out of the use or performance of the sample script and
# documentation (including, without limitation, damages for loss of business profits,
# business interruption, loss of business information, or other pecuniary loss), even if
# such person has been advised of the possibility of such damages.

import argparse
from typing import List
from scripts.file_utils import replace_text

import yaml
from yaml.resolver import Resolver
import os
import glob


# Prevent the interpreter from thinking "on" is a boolean
for ch in "OoYyNn":
    if len(Resolver.yaml_implicit_resolvers[ch]) == 1:
        del Resolver.yaml_implicit_resolvers[ch]
    else:
        Resolver.yaml_implicit_resolvers[ch] = [x for x in
                                                Resolver.yaml_implicit_resolvers[ch] if x[0] != 'tag:yaml.org,2002:bool']


def _process_refs(file):
    with open(file) as f:
        yaml_obj = yaml.safe_load(f)

        return _traverse_refs(file, yaml_obj)


def _resolve_refs(file, items):
    new_dict = {}
    if len(items) == 1 and isinstance(items[0], dict) and len(items[0]) == 1 and '$ref' in items[0]:
        # This allof contains a single ref. No need to inline, just remove the allof
        return {'$ref': items[0]['$ref']}
    for item in items:
        if isinstance(item, dict):
            for k, v in item.items():
                if k == '$ref':
                    ref_file = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(file)), v))
                    ref_dict = _process_refs(ref_file)

                    for kr, vr in ref_dict.items():
                        if kr in new_dict and isinstance(vr, dict) and isinstance(new_dict[kr], dict):
                            new_dict[kr] = {**new_dict[kr], **vr}
                        else:
                            new_dict[kr] = vr
                else:
                    if k in new_dict and isinstance(v, dict) and isinstance(new_dict[k], dict):
                        new_dict[k] = {**new_dict[k], **v}
                    else:
                        new_dict[k] = v
        else:
            raise Exception("Don't understand " + str(item))
    return new_dict


def _traverse_refs(file, obj):
    if isinstance(obj, list):
        new_list = []
        for li in obj:
            new_list.append(_traverse_refs(file, li))
        return new_list
    elif isinstance(obj, dict):
        new_dict = {}
        changed = True
        while changed:
            changed = False
            for k, v in obj.items():
                if k == 'allOf' and isinstance(v, list):
                    ref_dict = _resolve_refs(file, v)
                    del obj['allOf']
                    obj = {**obj, **ref_dict}
                    changed = True
                    break

        for k, v in obj.items():
                new_dict[k] = _traverse_refs(file, v)

        return new_dict
    else:
        return obj


def _fix_required(file):
    with open(file) as f:
        yaml_obj = yaml.safe_load(f)

        yaml_obj = _traverse_required(yaml_obj)
        return yaml_obj


def _traverse_required(obj):
    if isinstance(obj, list):
        new_list = []
        for li in obj:
            new_list.append(_traverse_required(li))
        return new_list
    elif isinstance(obj, dict):
        # Check if this defines an object
        if 'type' in obj and obj['type'] == 'object':
            # loop through the properties and check if they have 'required = true'
            required_props = []
            if 'properties' in obj:
                for k, v in obj['properties'].items():
                    if 'required' in v and v['required'] == True:
                        required_props.append(k)
                        del v['required']

            if len(required_props) > 0:
                obj['required'] = required_props

        for k, v in obj.items():
            obj[k] = _traverse_required(v)

        return obj
    else:
        return obj


def _normalize_relative_refs(file):
    with open(file) as f:
        yaml_obj = yaml.safe_load(f)

        yaml_obj = _traverse_relative_refs(file, yaml_obj)
        return yaml_obj


def _traverse_relative_refs(file, obj):
    if isinstance(obj, list):
        new_list = []
        for li in obj:
            new_list.append(_traverse_relative_refs(file, li))
        return new_list
    elif isinstance(obj, dict):
        # Check if this defines an object
        for k, v in obj.items():
            if k == '$ref' and not v.startswith('../'):
                obj[k] = os.path.join("../../", os.path.relpath(os.path.join(os.path.dirname(file), v), os.path.join(os.path.dirname(file), "../../")))
            else:
                obj[k] = _traverse_relative_refs(file, v)

        return obj
    else:
        return obj


def process_paths(paths: List):
    """
    Find all files in the given path and inline the contents of any referenced files

    :param paths: A list of path objects
    :return:
    """
    full_paths = [os.path.join(os.getcwd(), path) for path in paths]
    files = set()

    for path in full_paths:
        if os.path.isfile(path):
            fileName, fileExt = os.path.splitext(path)
            if fileExt == '.yaml':
                files.add(path)
        else:
            full_paths += glob.glob(path + '/*')

    # Normalized references to all be relative from same location
    for file in files:
        yaml_obj = _normalize_relative_refs(file)
        yaml_out = yaml.dump(yaml_obj)
        with open(file, "w") as f:
            f.write(yaml_out)

    # Inline appropriate references in the given paths
    for file in files:
        yaml_obj = _process_refs(file)
        yaml_out = yaml.dump(yaml_obj)
        with open(file, "w") as f:
            f.write(yaml_out)

    # Once references have been inlined, we need to convert from the old "required: true" style for properties to
    # the new "required: [ "a", "b", "c" ]" style
    for file in files:
        yaml_obj = _fix_required(file)
        yaml_out = yaml.dump(yaml_obj)
        with open(file, "w") as f:
            f.write(yaml_out)

    # Do any text replacing needed
    for file in files:
        # Handle properties with a truthy value for a name
        replace_text(file, ' on:', ' "on":')


def rename_array_yaml(paths: List):
    full_paths = [os.path.join(os.getcwd(), path) for path in paths]
    files = set()

    for path in full_paths:
        if os.path.isfile(path):
            fileName, fileExt = os.path.splitext(path)
            if fileExt == '.yaml':
                files.add(path)
        else:
            full_paths += glob.glob(path + '/*')

    # Do any text replacing needed
    for file in files:
        # Files named "array" cause problems with... arrays
        replace_text(file, r'/array\.yaml', '/arrays.yaml')
        if os.path.basename(file) == 'array.yaml':
            os.rename(file, os.path.join(os.path.dirname(file), 'arrays.yaml'))


def main():
    parser = argparse.ArgumentParser(description='Replace $ref= instances in yaml files with the contents of the reference')
    parser.add_argument('path', nargs='+', help='List of files or paths to process.')

    args = parser.parse_args()
    process_paths(args.path)


if __name__ == '__main__':
    main()

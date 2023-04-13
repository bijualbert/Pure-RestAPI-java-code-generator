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
import subprocess
from typing import List
import tempfile, shutil, os, re, glob
import urllib.request

from scripts import yaml_utils
from scripts.file_utils import replace_text
from scripts.language_handler import get_language_handler, get_config_file


def get_product_prefix(product):
    if product == "flasharray":
        return 'FA'
    if product == 'pure1':
        return 'Pure1-'

    raise Exception('Unknown product: ' + product)


def determine_versions(source_dir, product, versions):
    # Determine Versions
    if (versions is None or len(versions) == 0):
        prefix = get_product_prefix(product)
        versions = []
        for entry in os.listdir(os.path.join(source_dir, "specs")):
            filename, extension = os.path.splitext(entry)
            if extension == '.yaml' and filename.endswith('.spec'):
                filename = filename[:-len('.spec')]
                if filename.startswith(prefix) and (filename[len(prefix)+2:].isdigit()):
                    versions.append(filename[len(prefix):])

    return versions


def fix_camel_case_issues(directory):
    for entry in os.listdir(directory):
        filename = os.path.join(directory, entry)
        if os.path.isfile(filename):
            _, extension = os.path.splitext(entry)
            if extension == '.yaml':
                replace_text(filename, "KMIP", "Kmip")
                replace_text(filename, "SAML2 SSO", "Saml2Sso")
                replace_text(filename, "SAML2-SSO", "Saml2Sso")
                replace_text(filename, "SNMPAgent", "SnmpAgent")
                replace_text(filename, "APIClient", "ApiClient")
                replace_text(filename, "SMI-S", "Smis")
                replace_text(filename, "DNS", "Dns")

        elif os.path.isdir(filename):
            fix_camel_case_issues(filename)


def build(source: str, build_output_root_dir: str, product: str, language: str, versions: List[str],
          swagger_jar_url: str, java_binary: str, artifact_version: str):

    prefix = get_product_prefix(product)
    launguage_handler = get_language_handler(product, language)


    # Copy source files to temporary location
    working_dir = tempfile.mkdtemp()
    print("Working in directory: " + working_dir)

    print("Downloading " + swagger_jar_url)
    swagger_jar = os.path.join(working_dir, 'swagger-codegen-cli.jar')
    urllib.request.urlretrieve(swagger_jar_url, swagger_jar)

    source_dir = os.path.join(working_dir, 'source')
    config_dir = os.path.join(working_dir, 'config')

    print("Making a copy of the swagger files")
    shutil.copytree(source, source_dir, dirs_exist_ok=True)

    versions = determine_versions(source_dir, product, versions)
    versions.sort()
    print("Generating config for versions: " + str(versions))

    os.mkdir(config_dir)
    launguage_handler.generate_configs(config_dir, language, versions, artifact_version)
    print("Fixing camel case issues")
    fix_camel_case_issues(source_dir)

    # Process the yaml files for models and responses to make them work correctly with code generation
    print("Fixing references in models and responses")
    yaml_utils.process_paths(glob.glob(os.path.join(source_dir, 'models', prefix + '*')))
    yaml_utils.process_paths(glob.glob(os.path.join(source_dir, 'responses', prefix + '*')))

    print("Renaming files named 'array.yaml'")
    yaml_utils.rename_array_yaml(glob.glob(os.path.join(source_dir, 'models', prefix + '*')))
    yaml_utils.rename_array_yaml(glob.glob(os.path.join(source_dir, 'responses', prefix + '*')))
    yaml_utils.rename_array_yaml(glob.glob(os.path.join(source_dir, 'specs', prefix + '*')))

    first_version = True

    for version in versions:
        build_output_dir = os.path.join(build_output_root_dir, f"{version}")
        if os.path.isdir(build_output_dir) and len(os.listdir(build_output_dir)) != 0:
            print("WARNING: Target directory not empty: " + build_output_dir)
            print("WARNING: Skipping version: " + version)
            continue

        generator_output_dir = os.path.join(working_dir, f"client_{version}")
        os.mkdir(generator_output_dir)

        print("Generating client for version " + version)
        process = [java_binary,
                   '-DapiTests=false',
                   '-DmodelTests=false',
                   '-DapiDocs=false',
                   '-DmodelDocs=false',
                   '-jar',
                   swagger_jar,
                   'generate',
                   '-i',
                   os.path.join(source_dir, 'specs', f"{prefix}{version}.spec.yaml"),
                   '-o',
                   generator_output_dir,
                   '-l',
                   language,
                   '-c',
                   get_config_file(config_dir, version)]
        print("Running Swagger Codegen with following command: " + " ".join(process))
        result = subprocess.run(process,
                                capture_output=True,
                                text=True)

        try:
            result.check_returncode()
        except subprocess.CalledProcessError:
            print(result.stdout)
            print(result.stderr)
            raise

        launguage_handler.post_process(version, generator_output_dir, working_dir, build_output_root_dir, artifact_version,
                                       first_version)

        os.makedirs(build_output_dir)
        shutil.copytree(generator_output_dir, build_output_dir, dirs_exist_ok=True)

        print("Generated SDK available at: " + build_output_dir)
        first_version = False

    print("Cleaning up")
    shutil.rmtree(working_dir)


def main():
    parser = argparse.ArgumentParser(description='Build FlashArray REST 2 SDK from swagger files')
    parser.add_argument('source', help='Location of Swagger spec files')
    parser.add_argument('target', help='Directory to put generated clients')
    parser.add_argument('--product', '-p', choices=['flasharray', 'pure1'],help='Product to build.',
                        default='flasharray', required=False)
    parser.add_argument('--versions', '-v', nargs='+', help='List of versions to build. Omit to build all versions.',
                        default=None, required=False)
    parser.add_argument('--language', '-l', help='Language to build. Defaults to "java".', default='java',
                        required=False)
    parser.add_argument('--java-binary', '-j', help='Location of the Java binary. Defaults to "/usr/bin/java".',
                        default='/usr/bin/java', required=False)
    parser.add_argument('--swagger-gen', '-s', help='URL of swagger-codegen-cli jar file.',
                        default='https://repo1.maven.org/maven2/io/swagger/swagger-codegen-cli/2.4.28/swagger-codegen-cli-2.4.28.jar',
                        required=False)
    parser.add_argument('--artifact-version', help='Version of generated artifact', default='1.0.0', required=False)

    args = parser.parse_args()

    if not os.path.isfile(args.java_binary):
        print("ERROR: --java-binary must be a path to a java executable")
        exit(1)

    build(args.source, args.target, args.product, args.language, args.versions, args.swagger_gen, args.java_binary,
          args.artifact_version)


if __name__ == '__main__':
    main()

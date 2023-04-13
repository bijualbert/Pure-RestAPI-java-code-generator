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

from scripts.file_utils import replace_text
import shutil, os, re, glob
import json


def get_config_file(config_dir, version):
    return os.path.join(config_dir, f"config{version}.json")


class LaunguageHandlerBase:
    def __init__(self, product):
        self.product = product
        pass

    def generate_configs(self, config_dir, language, versions, artifact_version):
        """Generate the config files used for this language for each version"""
        pass

    def post_process(self, version, generator_output_dir, working_dir, build_output_root_dir, artifact_version,
                     first_version=False):
        """
        Run any post-processing required on generated code

        :param generator_output_dir: directory containing the generator output for this version
        :param working_dir: temp directory for staging work
        :param build_output_root_dir: target directory for output packages
        :param artifact_version: version of this artifact for package managers
        :param first_version: True if this is the first version generated. Useful for tasks that only
        need to be run once for all versions

        :return:
        """
        pass


class JavaHandler(LaunguageHandlerBase):
    def __init__(self, product):
        super().__init__(product)
        self.common_artifact_id = f'{self.product}-rest-client-common'

    def _get_version_for_package(self, version):
        return f"v{version.replace('.', '_')}"

    def _get_artifact_id(self, version):
        return f"{self.product}-rest-{version}-client"

    def _get_model_package(self, version):
        return f"com.purestorage.rest.{self.product}.{self._get_version_for_package(version)}.model"

    def _get_api_package(self, version):
        return f"com.purestorage.rest.{self.product}.{self._get_version_for_package(version)}.api"

    @staticmethod
    def _fix_java_compilation_issues(directory):
        for entry in os.listdir(directory):
            filename = os.path.join(directory, entry)
            if os.path.isfile(filename):
                file, extension = os.path.splitext(entry)
                if file.startswith('Array') and extension == '.java':
                    replace_text(filename, r"import java.util.Arrays\;", "")
                if extension == '.java':
                    replace_text(filename, r"@javax.annotation.Generated.+", "")

            elif os.path.isdir(filename):
                JavaHandler._fix_java_compilation_issues(filename)

    def _add_common_dependency_to_pom(self, pom_file, artifact_version):
        with open(pom_file, 'r+') as fd:
            contents = fd.readlines()
            for index, line in enumerate(contents):
                if '<dependencies>' in line:
                    contents.insert(index + 1, '        <dependency>\n')
                    contents.insert(index + 2, '            <groupId>com.purestorage.rest</groupId>\n')
                    contents.insert(index + 3, f'            <artifactId>{self.common_artifact_id}</artifactId>\n')
                    contents.insert(index + 4, f'            <version>{artifact_version}</version>\n')
                    contents.insert(index + 5, '        </dependency>\n')
                    break
            fd.seek(0)
            fd.writelines(contents)

    def _check_duplicate_class(self, original, duplicate):
        original_class_name = os.path.basename(original)
        duplicate_class_name = os.path.basename(duplicate)

        original_var_name = original_class_name[0].lower() + original_class_name[1:]
        duplicate_var_name = duplicate_class_name[0].lower() + duplicate_class_name[1:]

        with open(original + '.java', 'r') as f:
            original_contents = f.readlines()

        with open(duplicate + '.java', 'r') as f:
            duplicate_contents = f.readlines()

        if len(original_contents) != len(duplicate_contents):
            return False

        for index, original_line in enumerate(original_contents):
            duplicate_line = duplicate_contents[index]
            duplicate_line = re.sub(f"([^a-zA-z0-9])({duplicate_class_name})([^a-zA-z0-9])", r"\1" + original_class_name + r"\3", duplicate_line)
            duplicate_line = re.sub(f"([^a-zA-z0-9])({duplicate_var_name})([^a-zA-z0-9])", r"\1" + original_var_name + r"\3", duplicate_line)
            if duplicate_line != original_line:
                print(original_line)
                print(duplicate_line)
                return False

        return True

    def _remove_duplicate_class(self, files, original, duplicate, replace_var_names=True):
        original_class_name = os.path.basename(original)
        duplicate_class_name = os.path.basename(duplicate)

        original_var_name = original_class_name[0].lower() + original_class_name[1:]
        duplicate_var_name = duplicate_class_name[0].lower() + duplicate_class_name[1:]

        updated_file_count = 0
        for fileName, filePath in files.items():
            if os.path.isfile(filePath):
                with open(filePath, 'r') as f:
                    contents = f.readlines()
                new_contents = []
                changed = False
                for index, line in enumerate(contents):
                    line = re.sub(f"([^a-zA-z0-9])(?<!java\.util\.)({duplicate_class_name})([^a-zA-z0-9])", r"\1" + original_class_name + r"\3", line)
                    if replace_var_names:
                        line = re.sub(f"([^a-zA-z0-9\"])({duplicate_var_name})([^a-zA-z0-9\"])", r"\1" + original_var_name + r"\3", line)
                    if line != contents[index]:
                        changed = True

                    # These changes can lead to duplicated import statements. Handle that as well
                    if not line.startswith('import') or index == 0 or line != contents[index - 1]:
                        new_contents.append(line)
                if changed:
                    updated_file_count += 1
                    with open(filePath, 'w') as f:
                        f.writelines(new_contents)

        return updated_file_count

    def _remove_duplicate_models(self, source_root):
        full_paths = glob.glob(source_root + '/**/*.java', recursive=True)
        files = {}

        for path in full_paths:
            if os.path.isfile(path):
                fileName, fileExt = os.path.splitext(path)
                if fileExt == '.java':
                    files[fileName] = path

        total_duplicate_classes = 0
        total_updated_files = 0
        duplicates = set()
        for k, v in files.items():
            next = 2
            found = True
            while (found):
                duplicate_name = k + str(next)
                found = duplicate_name not in duplicates and duplicate_name in files
                if found:
                    if self._check_duplicate_class(k, duplicate_name):
                        total_duplicate_classes += 1
                        os.remove(files[duplicate_name])
                        total_updated_files += self._remove_duplicate_class(files, k, duplicate_name)
                        duplicates.add(duplicate_name)
                    next += 1

        for k, v in files.items():
            duplicate_name = k + 's'
            found = duplicate_name not in duplicates and duplicate_name in files
            if found:
                if self._check_duplicate_class(k, duplicate_name):
                    total_duplicate_classes += 1
                    os.remove(files[duplicate_name])
                    # Don't replace variable names if we've found an "Arrays" class and an "Array" class
                    total_updated_files += self._remove_duplicate_class(files, k, duplicate_name, False)
                    duplicates.add(duplicate_name)


        print(f"  Found {total_duplicate_classes} duplicate classes")
        print(f"  Updated {total_updated_files} files to remove references to duplicates")

    def generate_configs(self, config_dir, language, versions, artifact_version):
        """Generate the config files used for this language for each version"""
        # Write configs
        for version in versions:
            config_dict = {
                'groupId': "com.purestorage.rest",
                'invokerPackage': f"com.purestorage.rest.{self.product}.common",
                'modelPackage': self._get_model_package(version),
                'apiPackage': self._get_api_package(version),
                'artifactId': self._get_artifact_id(version),
                'artifactVersion': artifact_version
            }
            with open(get_config_file(config_dir, version), 'w') as config_file:
                json.dump(config_dict, config_file)
        pass

    def post_process(self, version, generator_output_dir, working_dir, build_output_root_dir, artifact_version,
                     first_version=False):
        """
        Run any post-processing required on generated code

        :param generator_output_dir: directory containing the generator output for this version
        :param working_dir: temp directory for staging work
        :param build_output_root_dir: target directory for output packages
        :param artifact_version: version of this artifact for package managers
        :param first_version: True if this is the first version generated. Useful for tasks that only
        need to be run once for all versions

        :return:
        """
        print("Fixing Java compilation issues")
        self._fix_java_compilation_issues(working_dir)

        # The readme has very wrong documentation. Remove it to prevent confusion
        os.remove(os.path.join(generator_output_dir, "README.md"))

        if self.product == 'flasharray':
            if first_version:
                print("Extracting common classes")
                # Copy out the common java files to a separate java project
                common_path = os.path.join(working_dir, "common")
                shutil.copytree(generator_output_dir, common_path, dirs_exist_ok=True)
                shutil.rmtree(os.path.join(common_path, "src", "main", "java", "com", "purestorage", "rest", self.product, self._get_version_for_package(version)))
                tests_path = os.path.join(common_path, "src", "test")
                if os.path.isdir(tests_path):
                    shutil.rmtree(tests_path)
                replace_text(os.path.join(common_path, 'pom.xml'), self._get_artifact_id(version), self.common_artifact_id)
                replace_text(
                    os.path.join(common_path, "src", "main", "java", "com", "purestorage", "rest", self.product, "common", "JSON.java"),
                    f"import {self._get_model_package(version)}.*;", "")
                common_target_path = os.path.join(build_output_root_dir, "common")
                os.makedirs(common_target_path)
                shutil.copytree(common_path, common_target_path, dirs_exist_ok=True)

                print("Common classes available at: " + common_target_path)

            shutil.rmtree(os.path.join(generator_output_dir, "src", "main", "java", "com", "purestorage", "rest", self.product, "common"))
            self._add_common_dependency_to_pom(os.path.join(generator_output_dir, 'pom.xml'), artifact_version)
        print("Removing duplicate models")
        self._remove_duplicate_models((os.path.join(generator_output_dir, "src")))


def get_language_handler(product: str, language: str) -> LaunguageHandlerBase:
    if language == 'java':
        return JavaHandler(product)

    return LaunguageHandlerBase(product)

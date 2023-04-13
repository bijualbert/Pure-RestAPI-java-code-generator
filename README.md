# rest-2-client-generator

These scripts perform the necessary modifications to use the Swagger API documentation for FlashArray storage
arrays for code generation. 

## Background
Pure Storage FlashArray and FlashBlade REST APIs have extensive documentation which can be viewed at
https://github.com/PureStorage-OpenConnect/swagger. While the yaml files used to generate this UI work perfectly
well for that use case, the Swagger Codegen tools have different expectations of the format and content
of these yaml files. These scripts manipulate those files such that they can be successfully passed into Swagger
Codegen, and then run the generation to produce a client SDK for use in other tools.

## Try Tt:
### Requirements:
* Python 3 (tested using python 3.9.9)
* Java JRE 1.8+
OR
* Docker

### Steps:

#### Local Build
* Clone the git repo at https://github.com/PureStorage-OpenConnect/swagger, or download it in some other way
* Install the python requirements with `python3 -m pip install -r requirements.txt`
* Run `python3 build.py <source> <target> [options]` with the following parameters
  * source: source directory containing the swagger spec files. This should be the `html` subdirectory of the swagger repo
  * target: target directory where the generated files will be output
  * options:
    * `--verions VERSIONS [VERSIONS ...]`: List of versions to build. Omit to build all versions.
    * `--language LANGUAGE`: Language to build. Defaults to `java`
    * `--java-binary JAVA_BINARY`: Location of the Java binary. Defaults to `/usr/bin/java`. If on Windows, specify the 
location of the `java.exe` file to use when running Swagger Codegen
    * `--swagger-gen SWAGGER_GEN`: URL of swagger-codegen-cli jar file. Defaults to the latest tested build.
    * `--artifact-version`: Version of generated artifact. Defaults to 1.0.0

#### Docker Build
* Run `./build_docker.sh`
* Use any of the options specified above

### Sample Execution
```
$ python3 build.py ~/git/swagger/html/ ~/work/purest_gen/java/ --versions 2.13
Working in directory: /var/folders/zw/rr8stw2j3jxfcf17t84pnhxm0000gp/T/tmpc_0rc5hk
Downloading https://repo1.maven.org/maven2/io/swagger/swagger-codegen-cli/2.4.28/swagger-codegen-cli-2.4.28.jar
Making a copy of the swagger files
Generating config for versions: ['2.13']
Fixing camel case issues
Fixing references in models and responses
Generating client for version 2.13
Fixing array import issue
Generated SDK available at: ~/work/purest_gen/java/2.13
Cleaning up
```

## Modifications Made
The scripts perform the following modifications to the Pure Swagger yaml files:
* Fix camel case consistency issues. Some objects are referred to with different camel case schemes in different places.
For example, `SNMPAgent` and `SnmpAgent` are both used. Known instances of this are fixed so the generator code 
functions correctly. Without this step, the generator may, for example, place a class named `SnmpAgent` inside
`SNMPAgent.java`, which results in a compilation error.
* Fix references in models and responses. To reduce code duplication and copy/paste errors, the yaml files used
to document the REST APIs rely heavily on referencing other yaml files. For example, any time an object is referred
to by its reference, the properties of that reference are implemented in `models/FA2.0/_reference.yaml`. Unfortunately,
this level of referencing causes issues with the code generation package. To avoid these issues, all references in
the `models` and `responses` packages which appear inside an `allOf` element are resolved and inlined.
* Fix old-style 'required: true' properties with the correct `require: ['a', 'b', 'c']` form
* Normalize all references: Swagger Codegen appears to store all references in a hashmap with the reference path as
a key. However, it uses the relative path, so `_space.yaml` and `../../models/FA2.0/_space.yaml` will be treaded as
separate models. To reduce the problems caused by this, all references are re-written as relative to the spec root.
Since all yaml files are exactly two paths from that root, references work correctly in all cases

### Java
* Once generated, some Java class files reference the `Array` class created for the arrays APIs. These references
conflict with the `java.util.Array` import added by the generator. These imports are removed to resolve the compiler
issue.
* The generator adds the deprecated `@javax.annotation.Generated` annotation. These are removed.
* Even after normalizing references, some duplicate classes are generated. This seems to happen when a model is used
as both an input and in a response. The output classes are searched for duplicates with identical contents other than
class name. These are then consolidated. 

## Limitations
* While generation *should* work for any supported language, this package has only been thoroughly tested generating Java.
* Only FlashArray APIs are supported currently

## Next Steps
* Implement Java SDK wrappers to handle authentication in a user-friendly way
* Code samples
* FlashBlade support
* Pure1 support

## Links
* [Swagger Codegen](https://github.com/swagger-api/swagger-codegen)
* [Pure Swagger](https://github.com/PureStorage-OpenConnect/swagger)

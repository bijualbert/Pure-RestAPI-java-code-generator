FROM ubuntu:22.04
WORKDIR /source

RUN apt-get update && apt-get install -y openjdk-8-jdk curl python3 python3-pip git

RUN update-java-alternatives -s java-1.8.0-openjdk-amd64

COPY ./requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY ./build.py .
COPY ./docker_entrypoint.sh .
COPY ./scripts ./scripts

RUN ["chmod", "+x", "/source/docker_entrypoint.sh"]

ENTRYPOINT ["/source/docker_entrypoint.sh"]

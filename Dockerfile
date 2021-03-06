FROM python:3.8.8-slim-buster

# Set working directory
RUN mkdir /src
WORKDIR /src

RUN apt-get update -qq \
&& apt-get -y install sudo \
&& apt-get -y install apt-utils  \
&& apt-get -y install wget \
&& apt-get -y install gcc \
&& apt-get -y install git

# Install dumb-init
RUN wget -O /usr/local/bin/dumb-init https://github.com/Yelp/dumb-init/releases/download/v1.2.1/dumb-init_1.2.1_amd64
RUN chmod +x /usr/local/bin/dumb-init

# Install requirements
COPY ./requirements.txt /src/
RUN pip install -r /src/requirements.txt

# For some reason the install in requirements isn't picking up latest breaking change fix?
RUN pip install git+https://github.com/Rapptz/discord.py@master -U

# Bundle app source
ADD . /src

# Set default container command
ENTRYPOINT ["dumb-init", "--", "python", "-m", "watcher", "launcher"]

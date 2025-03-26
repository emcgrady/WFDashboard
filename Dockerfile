# syntax=docker/dockerfile:1
FROM docker.io/continuumio/miniconda3:latest
ENV WDIR=/data 
#ENV USER=dmwmmonit
RUN mkdir $WDIR && cd $WDIR
#RUN echo "%$USER ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
#RUN useradd ${USER} && install -o ${USER} -d ${WDIR}
#ENV X509_USER_PROXY=/tmp/x509up_u$(UID)
#ENV X509_USER_CERT=~/.globus/usercert.pem
#ENV X509_USER_KEY=~/.globus/userkey.pem
RUN git clone https://github.com/emcgrady/WFDashboard.git
ADD environment.yml $WDIR
RUN conda env create -f environment.yml
RUN conda activate wfdashboard
RUN git clone https://github.com/dmwm/CMSSpark.git
RUN pip install -r $(pwd)/CMSSpark/requirements.txt
RUN export PYTHONPATH="${PYTHONPATH}:$(pwd)/CMSSpark/src/python/CMSSpark"
ADD monit_pull.py $WDIR
RUN python monit_pull.py

# syntax=docker/dockerfile:1
#FROM python:3.10-slim
FROM almalinux:9
ENV WDIR=/data
RUN dnf -y install python3 python3-pip
RUN pip install opensearch-py
RUN pip install pandas
RUN pip install pycurl
RUN pip install rucio-clients
RUN pip install tqdm
RUN mkdir $WDIR 
WORKDIR $WDIR
ENV X509_USER_PROXY=/tmp/x509up_u$(UID)
RUN dnf search openssh
RUN dnf -y install git
RUN git clone https://github.com/emcgrady/WFDashboard.git
RUN git clone https://github.com/dmwm/CMSSpark.git
RUN pip install -r $(pwd)/CMSSpark/requirements.txt
RUN export PYTHONPATH="${PYTHONPATH}:$(pwd)/CMSSpark/src/python/CMSSpark"
ADD monit_pull.py $WDIR
ENTRYPOINT ["python", "monit_pull.py"]
from rucio.client.client import Client
from osearch import osearch
from pandas import DataFrame
from getpass import getpass
from pycurl import Curl
from json import loads
from io import BytesIO
from tqdm import tqdm
from time import time

import os 
import pwd

client  = Client()
timestamp = time()

states = [
    'new',
    'assignment-approved',
    'assigned',
    'staging',
    'staged',
    'acquired',
    'running-open',
    'running-closed',
    'completed',
    'closed-out',
    'announced',
    'aborted',
    'aborted-completed',
    'failed',
    'rejected',
    'force-complete',
]

def getX509():
    "Helper function to get x509 from env or tmp file"
    proxy = os.environ.get('X509_USER_PROXY', '')
    if proxy: 
        return proxy, proxy
    else: 
        proxy = '/tmp/x509up_u%s' % pwd.getpwuid(os.getuid()).pw_uid
        if os.path.isfile(proxy):
            return proxy, proxy
        else: 
            certFile = os.environ.get('X509_USER_CERT', '')
            keyFile = os.environ.get('X509_USER_KEY', '')
            if certFile and keyFile:
                return certFile, keyFile
            else: 
                return '', ''

def get_index_schema():
    return {
        "settings": {"index": {"number_of_shards": "1", "number_of_replicas": "1"}},
        "mappings": {
            "properties": {
                "state": {"type": "keyword"}, 
                "numWFs": {"type": "long"},
                "inputHeld_TB": {"type": "long"},
                "outputHeld_TB": {"type": "long"},
                "requestType": {"type": "keyword"},
                "campaign": {"type": "keyword"},
                "timestamp": {"type": "date", "format": "epoch_second"}
            }
        }
    }

def pull():
    params = ['RequestTransition',
              'Campaign',
              'RequestType',
              'OriginalRequestType',
              'InputDataset',
              'OutputDatasets',
              'OriginalRequestName'
             ]
    mask = ''
    cert, key = getX509()
    for param in params: 
        mask = f'{mask}&mask={param}'
    link   = f'https://cmsweb.cern.ch/wmstatsserver/data/filtered_requests?{mask}'
    buffer = BytesIO()
    c      = Curl()
    c.setopt(c.URL, link)
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.CAINFO, None)
    c.setopt(c.SSLCERT, cert)
    c.setopt(c.SSLKEY,  key)
    c.setopt(c.WRITEDATA, buffer)
    c.setopt(c.SSL_VERIFYPEER, False)
    c.perform()
    c.close()
    body = buffer.getvalue()
    body = body.decode('iso-8859-1')
    return loads(body)['result']

def sum_data(name, InLocks, OutLocks):
    uni      = []
    InTotal  = 0
    OutTotal = 0
    
    for lock in InLocks:
        if (lock['rse'], lock['name']) not in uni:
            uni = uni + [(lock['rse'], lock['name'])]
            if lock['bytes'] is not None:
                InTotal += lock['bytes']
                    
    for lock in OutLocks:
        if (lock['rse'], lock['name']) not in uni:
            uni = uni + [(lock['rse'], lock['name'])]
            if lock['bytes'] is not None:
                OutTotal += lock['bytes']
    return InTotal/1e12, OutTotal/1e12

def df_builder(start):
    
    columns = ['RequestName', 
               'CurrentState', 
               'InputLocked', 
               'OutputLocked', 
               'RequestType',
               'Campaign', 
               'InputDataset', 
               'OutputDatasets']

    df = DataFrame(index=start.index, columns = columns)

    for i, row in tqdm(df.iterrows(), total=len(df), unit='wf'):
        row.RequestName = start.RequestName.iloc[i]
        row.RequestType = start.RequestType.iloc[i]

        if type(start.Campaign.iloc[i]) == str:
            row.Campaign = start.Campaign.iloc[i]
        else: 
            row.Campaign = start.Campaign.iloc[i][0]
            
        row.CurrentState = start.iloc[i].RequestTransition[-1]['Status']

        if start.RequestName.str.contains(start.OriginalRequestName.fillna(' ').iloc[i]).any():
            row.InputLocked  = 0.
            row.OutputLocked = 0.
            continue

        row.InputDataset   = start.InputDataset.iloc[i]
        row.OutputDatasets = start.OutputDatasets.iloc[i]
        n_retries = 5

        while n_retries > 0:
            try:
                InLocks  = []
                OutLocks = []

                if row.InputDataset: 
                    if type(row.InputDataset) == str:
                        InLocks = InLocks + client.get_locks_for_dids([{'scope': 'cms',
                                                                        'name'  : row.InputDataset}],
                                                                      account='wmcore_transferor')
                    else:
                        for dataset in row.InputDataset:
                            InLocks = InLocks + client.get_locks_for_dids([{'scope': 'cms', 
                                                                            'name'  : dataset}],
                                                                          account='wmcore_transferor')
                if row.OutputDatasets: 
                    for dataset in row.OutputDatasets:
                        OutLocks = OutLocks + client.get_locks_for_dids([{'scope': 'cms', 
                                                                          'name'  : dataset}],
                                                                        account='wma_prod')
            except:
                n_retries -= 1
                continue
            else:
                break

        row.InputLocked, row.OutputLocked = sum_data(row.RequestName, InLocks, OutLocks)

    return df
    
def build_docs(df):
    docs = []
    index = 0
    for campaign in df.Campaign.unique():
        temp = df.loc[df.Campaign == campaign]
        for RequestType in temp.RequestType.unique():
            for state in states: 
                temp1 = temp.loc[(temp.CurrentState == state) & (temp.RequestType == RequestType)]
                docs += [{}]
                docs[index]['state'] = state
                docs[index]['timestamp'] = timestamp
                docs[index]['numWFs'] = len(temp1)
                docs[index]['inputHeld_TB'] = temp1.InputLocked.sum()
                docs[index]['outputHeld_TB'] = temp1.OutputLocked.sum()
                docs[index]['requestType'] = RequestType
                docs[index]['campaign'] = campaign
                index += 1
    return docs

def main(): 
    start = DataFrame(pull())
    df = df_builder(start)
    docs = build_docs(df)
        
    _index_template = 'test-wfs'
    client = osearch.get_es_client("os-cms.cern.ch/os", 'secret_opensearch.txt', get_index_schema())
    idx = client.get_or_create_index(timestamp=time(), index_template=_index_template, index_mod="d")
    
    for doc in docs: 
        client.send(idx, doc, metadata=None, batch_size=10000, drop_nulls=False)
    
if __name__ == '__main__':
    main()
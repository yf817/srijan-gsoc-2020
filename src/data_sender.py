import yaml
import subprocess
from time import time
# syft dependencies
import syft as sy

#########<syft==0.2.8>#######################
# # Dynamic FL -->
from syft.grid.clients.data_centric_fl_client import DataCentricFLClient
import torch
import time
import numpy as np
import os
import json

NETWORK_IMAGE = 'srijanverma44/grid-network:v028'
NODE_IMAGE = 'srijanverma44/grid-node:v028'
DOCKER_START_TIME = 10
DATA_SEND_TIME = 2

class Preprocess:

    '''
    Class for conversion to tensor, docker initializer & docker stop
    '''

    def tensor_converter(self, a):
        datasets = []
        labels = []
        for key, val in a.items():
            data, label = zip(*a[key])
            label = np.array(label)
            data = np.array(data)
            data, label = np.vstack(data).astype(np.uint8), np.vstack(label).astype(np.uint8)
            label = label.reshape(label.shape[0])

            # Convert numpy array to torch tensors -->
            data = torch.from_numpy(data)
            label = torch.from_numpy(label)

            data = torch.tensor(data, dtype=torch.float32)
            label = torch.tensor(label, dtype=torch.int64)

            datasets.append(data)
            labels.append(label)

        return datasets, labels

    def docker_compose_generator(self, n):

        doc = {'version': '3',
               'services': {'network': {'image': NETWORK_IMAGE,
                                        'environment': ['PORT=5000',
                                                        'SECRET_KEY=ineedtoputasecrethere',
                                                        'DATABASE_URL=sqlite:///databasenetwork.db'],
                                        'ports': ['5000:5000']}}}

        _ports = [str(i) for i in range(3000, 3000 + n, 1)]

        for i in range(n):
            doc['services'].update(
                {'h{}'.format(i + 1): {'image': NODE_IMAGE,
                                       'environment': ['NODE_ID=h{}'.format(i + 1),
                                                       'ADDRESS=http://h{0}:{1}/'.format(i + 1, _ports[i]),
                                                       'PORT={}'.format(_ports[i]),
                                                       'NETWORK=http://network:5000',
                                                       'DATABASE_URL=sqlite:///databasenode.db'],
                                       'depends_on': ["network"],
                                       'ports': ['{0}:{0}'.format(_ports[i])]}
                 })

        with open('docker-compose.yml', 'w') as f:
            yaml.dump(doc, f)

        return _ports

    def docker_initializer(self, SWARM = 'no'):

        # For switching between compose & stack
        if SWARM == 'no':
            cmd = ['docker-compose', '-f', 'docker-compose.yml', 'up', '-d']
        elif SWARM == 'yes':
            cmd = ['docker', 'stack', 'deploy']


        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print('---<STARTING DOCKER IMAGE>----')
        out, error = p.communicate()
        print('====DOCKER STARTED!=======')
        time.sleep(DOCKER_START_TIME)

    def docker_kill(self):
        print('---<STOPPING DOCKER NODE/NETWORK CONTAINERS>----')
        os.system('docker rm $(docker stop $(docker ps -a -q --filter ancestor=srijanverma44/grid-node:v028 --format="{{.ID}}"))')
        os.system('docker rm $(docker stop $(docker ps -a -q --filter ancestor=srijanverma44/grid-network:v028 --format="{{.ID}}"))')

    def save_metrics(self, metrics_dict, metrics_path, train_type, metrics_file_name):

        # Save metrics in metadata
        print('---<SAVING METRICS.....>----')
        if metrics_file_name is not None:
            with open(metrics_path + '/' + metrics_file_name + '.json', 'w') as f:
                json.dump(metrics_dict, f, indent=4)
        else:
            with open(metrics_path + '/{}_metrics.json'.format(train_type), 'w') as f:
                json.dump(metrics_dict, f, indent=4)


class DataSender:
    '''
    Class for sending data to nodes
    '''

    def send_client_data(self, _ports, datasets, labels):
        hook = sy.TorchHook(torch)

        # Connect directly to grid nodes
        nodes = ["ws://0.0.0.0:{}".format(i) for i in _ports]

        compute_nodes = []
        for node in nodes:
            # For syft 0.2.8 --> replace DynamicFLClient with DataCentricFLClient
            compute_nodes.append(DataCentricFLClient(hook, node))

        print(compute_nodes)

        tag_input = []
        tag_label = []

        for i in range(len(compute_nodes)):
            tag_input.append(datasets[i].tag("#X", "#gtex_v8", "#dataset").describe(
                "The input datapoints to the GTEx_V8 dataset."))
            tag_label.append(labels[i].tag("#Y", "#gtex_v8", "#dataset").describe(
                "The input labels to the GTEx_V8 dataset."))

        x_dataset = []
        y_dataset = []

        for i in range(len(compute_nodes)):
            x_dataset.append(tag_input[i].send(compute_nodes[i]))  # First chunk of dataset to h1
            y_dataset.append(tag_label[i].send(compute_nodes[i]))  # First chunk of labels to h1
            time.sleep(DATA_SEND_TIME)

        for i in range(len(compute_nodes)):
            compute_nodes[i].close()



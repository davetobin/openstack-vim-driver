import logging
import uuid
from neutronclient.v2_0 import client as neutronclient
from neutronclient.common import exceptions as neutronexceptions
from ignition.service.logging import logging_context
import osvimdriver.service.common as common

logger = logging.getLogger(__name__)

LOG_URI_PREFIX = '...'

class NeutronDriver():

    def __init__(self, session):
        self.__session = session
        self.__neutron_client = neutronclient.Client(session=self.__session)

    def __get_neutron_client(self):
        return self.__neutron_client

    def get_network_by_id(self, network_id,driver_request_id=None):
        if network_id is None:
            raise ValueError('network_id must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving network with id %s', network_id)
        try:
            external_request_id = str(uuid.uuid4())
            common._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/networks/' + network_id }, driver_request_id)
            result = neutron_client.show_network(network_id)
            common._generate_additional_logs(result, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)  
            return result['network']
        except Exception as e:
            common._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.status_code,'status_reason_phrase' : e.message }, driver_request_id)
            raise e


    def get_network_by_name(self, network_name,driver_request_id=None):
        if network_name is None:
            raise ValueError('network_name must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving network with name %s', network_name)
        external_request_id = str(uuid.uuid4())
        common._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/networks' }, driver_request_id)
        try:
            result = neutron_client.list_networks()
            common._generate_additional_logs(str(result), 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)
        except Exception as e:
            common._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.status_code,'status_reason_phrase' : e.message }, driver_request_id)
            raise e    
        matches = []
        for network in result['networks']:
            if network['name'] == network_name:
                matches.append(network)
        if len(matches) > 1:
            raise neutronexceptions.NeutronClientNoUniqueMatch(resource='Network',
                                                               name=network_name)
        elif len(matches) == 1:  
            return matches[0]
        else:
            raise neutronexceptions.NotFound(message='Unable to find network with name \'{0}\''.format(network_name))

    def get_subnet_by_id(self, subnet_id,driver_request_id=None):
        if subnet_id is None:
            raise ValueError('subnet_id must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving subnet with id %s', subnet_id)
        try:
            external_request_id = str(uuid.uuid4())
            common._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/subnets/' + subnet_id}, driver_request_id)
            result = neutron_client.show_subnet(subnet_id)
            common._generate_additional_logs(result, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)
            return result['subnet']
        except Exception as e:
            common._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.status_code,'status_reason_phrase' : e.message }, driver_request_id)
            raise e
    
    
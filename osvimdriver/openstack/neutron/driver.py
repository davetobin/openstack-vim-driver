import logging
import uuid
from neutronclient.v2_0 import client as neutronclient
from neutronclient.common import exceptions as neutronexceptions
from ignition.service.logging import logging_context

logger = logging.getLogger(__name__)

LOG_URI_PREFIX = '...'

class NeutronDriver():

    def __init__(self, session):
        self.__session = session
        self.__neutron_client = neutronclient.Client(session=self.__session)

    def __get_neutron_client(self):
        return self.__neutron_client

    def get_network_by_id(self, network_id):
        if network_id is None:
            raise ValueError('network_id must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving network with id %s', network_id)
        try:
            external_request_id = str(uuid.uuid4())
            driver_request_id  = str(uuid.uuid4())
            self._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/networks/' + network_id }, driver_request_id)
            result = neutron_client.show_network(network_id)
            self._generate_additional_logs(result, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)  
            return result['network']
        except Exception as e:
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.status_code,'status_reason_phrase' : e.message }, driver_request_id)
            raise e


    def get_network_by_name(self, network_name):
        if network_name is None:
            raise ValueError('network_name must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving network with name %s', network_name)
        external_request_id = str(uuid.uuid4())
        driver_request_id  = str(uuid.uuid4())
        self._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/networks' }, driver_request_id)
        try:
            result = neutron_client.list_networks()
            self._generate_additional_logs(str(result), 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)
        except Exception as e:
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
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

    def get_subnet_by_id(self, subnet_id):
        if subnet_id is None:
            raise ValueError('subnet_id must be provided')
        neutron_client = self.__get_neutron_client()
        logger.debug('Retrieving subnet with id %s', subnet_id)
        try:
            external_request_id = str(uuid.uuid4())
            driver_request_id  = str(uuid.uuid4())
            self._generate_additional_logs('', 'sent', external_request_id, '',
                                       'request', 'http', {'method' : 'get', 'uri' : LOG_URI_PREFIX +'/subnets/' + subnet_id}, driver_request_id)
            result = neutron_client.show_subnet(subnet_id)
            self._generate_additional_logs(result, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)
            return result['subnet']
        except Exception as e:
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.status_code,'status_reason_phrase' : e.message }, driver_request_id)
            raise e
    
    def _generate_additional_logs(self, message_data, message_direction, external_request_id, content_type,
                                  message_type, protocol, protocol_metadata, driver_request_id):
        try:   
            logging_context_dict = {'message_direction' : message_direction, 'tracectx.externalrequestid' : external_request_id, 'content_type' : content_type,
                                    'message_type' : message_type, 'protocol' : protocol, 'protocol_metadata' : str(protocol_metadata).replace("'", '\"'),'tracectx.driverrequestid' : driver_request_id }
            if driver_request_id is None:
                logging_context_dict.pop('tracectx.driverrequestid')
            if message_direction is None:
                logging_context_dict.pop('message_direction')
            if external_request_id is None:
                logging_context_dict.pop('tracectx.externalrequestid')
            if content_type is None:
                logging_context_dict.pop('content_type') 
            if message_type is None:
                logging_context_dict.pop('message_type')
            if protocol is None:
                logging_context_dict.pop('protocol')                  
            if protocol_metadata is None:
                logging_context_dict.pop('protocol_metadata')  
            logging_context.set_from_dict(logging_context_dict)
            logger.info(str(message_data).replace("'",'\"'))
        finally:
            if('message_direction' in logging_context.data):
                logging_context.data.pop("message_direction")
            if('tracectx.externalrequestid' in logging_context.data):
                logging_context.data.pop("tracectx.externalrequestid")
            if('content_type' in logging_context.data):
                logging_context.data.pop("content_type")
            if('message_type' in logging_context.data):
                logging_context.data.pop("message_type")
            if('protocol' in logging_context.data):
                logging_context.data.pop("protocol")
            if('protocol_metadata' in logging_context.data):
                logging_context.data.pop("protocol_metadata")
            if('tracectx.driverrequestid' in logging_context.data):
                logging_context.data.pop("tracectx.driverrequestid")

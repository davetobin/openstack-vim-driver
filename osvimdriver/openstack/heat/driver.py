import logging
import uuid
from heatclient import client as heatclient
from heatclient import exc as heatexc
from ignition.service.logging import logging_context

import osvimdriver.service.resourcedriver as rd

logger = logging.getLogger(__name__)


class StackNotFoundError(Exception):
    pass

LOG_URI_PREFIX = '...'

class HeatDriver():

    def __init__(self, session):
        self.__session = session
        self.__heat_client = heatclient.Client('1', session=self.__session)

    def __get_heat_client(self):
        return self.__heat_client

    def create_stack(self, stack_name, heat_template, input_properties=None,  files=None,driver_request_id=None ):
        if input_properties is None:
            input_properties = {}
        if files is None:
            files = {}
        if stack_name is None:
            raise ValueError('stack_name must be provided')
        if heat_template is None:
            raise ValueError('heat_template must be provided')
        heat_client = self.__get_heat_client()
        logger.debug('Creating stack with name %s', stack_name)

        external_request_id = str(uuid.uuid4())

        reqbody_dict = {"stack_name" : stack_name, "template" : heat_template, "parameters" : input_properties, "files" : files}
        self._generate_additional_logs(reqbody_dict, 'sent', external_request_id, 'application/json',
                                       'request', 'http', {'method' : 'post', 'uri' : LOG_URI_PREFIX +'/stacks'}, driver_request_id)
        try:
            create_result = heat_client.stacks.create(stack_name=stack_name, template=heat_template, parameters=input_properties, files=files)
            stack_id = create_result['stack']['id']
            driver_request_id = rd.build_request_id(rd.CREATE_REQUEST_PREFIX, str(stack_id))
            self._generate_additional_logs(create_result, 'received', external_request_id, 'application/json',
                                       'response', 'http', {'status_code' : 201,'status_reason_phrase' : 'Created'}, driver_request_id)
            logger.debug('Stack with name %s created and assigned id %s', stack_name, stack_id)
            return stack_id
        except (heatexc.HTTPNotFound,heatexc.HTTPBadRequest) as e:
            status_reason_phrase = 'Not Found'
            if  e.code != 404:
                status_reason_phrase = 'Bad Request'
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.code,'status_reason_phrase' : status_reason_phrase}, driver_request_id)
            raise e

    def delete_stack(self, stack_id, driver_request_id=None):
        if stack_id is None:
            raise ValueError('stack_id must be provided')
        heat_client = self.__get_heat_client()
        logger.debug('Deleting stack with id %s', stack_id)
        try:
            external_request_id = str(uuid.uuid4())
           
            self._generate_additional_logs('', 'sent', external_request_id, '',
                                        'request', 'http', {'method':'delete', 'uri' : LOG_URI_PREFIX + '/stacks/' + stack_id}, driver_request_id)
            delete_result = heat_client.stacks.delete(stack_id)
            result = ''
            if delete_result != None:   
                result = delete_result
            self._generate_additional_logs(result, 'received', external_request_id, '',
                                       'response', 'http', {'status_code' : 204,'status_reason_phrase' : 'No Content'}, driver_request_id)
        except (heatexc.HTTPNotFound,heatexc.HTTPBadRequest) as e:
            status_reason_phrase = 'Not Found'
            if  e.code != 404:
                status_reason_phrase = 'Bad Request'
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.code,'status_reason_phrase' : status_reason_phrase}, driver_request_id)
            raise StackNotFoundError(str(e)) from e

    def get_stack(self, stack_id, driver_request_id=None):
        if stack_id is None:
            raise ValueError('stack_id must be provided')
        heat_client = self.__get_heat_client()
        logger.debug('Retrieving stack with id %s', stack_id)
        try:
            external_request_id = str(uuid.uuid4())
            self._generate_additional_logs('', 'sent', external_request_id, '',
                                        'request', 'http', {'method':'get', 'uri' : LOG_URI_PREFIX + '/stacks/' + stack_id}, driver_request_id)
            result = heat_client.stacks.get(stack_id)
           
            self._generate_additional_logs(str(result).removeprefix('<Stack').removesuffix('>'), 'received', external_request_id, 'application/json',
                                       'response', 'http', {'status_code' : 200, 'status_reason_phrase' : 'ok'}, driver_request_id)  
        except (heatexc.HTTPNotFound, heatexc.HTTPBadRequest)  as e:
            status_reason_phrase = 'Not Found'
            if  e.code != 404:
                status_reason_phrase = 'Bad Request'
            self._generate_additional_logs(e, 'received', external_request_id, 'plain/text',
                                       'response', 'http', {'status_code' : e.code,'status_reason_phrase' : status_reason_phrase}, driver_request_id)
            raise StackNotFoundError(str(e)) from e
        return result.to_dict()

    def check_stack(self, stack_id):
        if stack_id is None:
            raise ValueError('stack_id must be provided')
        heat_client = self.__get_heat_client()
        logger.debug('Checking stack with id %s', stack_id)
        try:
            heat_client.actions.check(stack_id)
        except heatexc.HTTPNotFound as e:
            raise StackNotFoundError(str(e)) from e
                      
    def get_stacks(self):
        heat_client = self.__get_heat_client()
        logger.debug('Retrieving stacks %s')
        result = heat_client.stacks.list()
        return result

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
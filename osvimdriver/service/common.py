from venv import logger
from ignition.service.logging import logging_context


def _generate_additional_logs(message_data, message_direction, external_request_id, content_type,
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
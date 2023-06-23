import unittest
import uuid
import tempfile
import shutil
import os
from unittest.mock import patch, MagicMock, ANY
from ignition.service.resourcedriver import InfrastructureNotFoundError, InvalidDriverFilesError, InvalidRequestError, ResourceDriverError
from ignition.model.references import FindReferenceResponse, FindReferenceResult
from ignition.model.associated_topology import AssociatedTopology
from ignition.model.lifecycle import LifecycleExecution, LifecycleExecuteResponse
from ignition.utils.file import DirectoryTree
from osvimdriver.service.resourcedriver import ResourceDriverHandler, StackNameCreator, PropertiesMerger, AdditionalResourceDriverProperties, AdoptProperties
from osvimdriver.service.tosca import ToscaValidationError
from osvimdriver.tosca.discover import DiscoveryResult, NotDiscoveredError
from osvimdriver.openstack.heat.driver import StackNotFoundError
from tests.unit.testutils.constants import TOSCA_TEMPLATES_PATH, TOSCA_HELLO_WORLD_FILE
from ignition.utils.propvaluemap import PropValueMap

class TestPropertiesMerger(unittest.TestCase):

    def test_merge(self):
        merger = PropertiesMerger()
        result = merger.merge(
            PropValueMap({
                'propA': {'type': 'string', 'value': 'propA'}, 
                'propB': {'type': 'integer', 'value': 1},
                'propC': {'type': 'float', 'value': 1.6},
                'propD': {'type': 'boolean', 'value': True},
                'propE': {'type': 'timestamp', 'value': '2020-11-23T11:49:33.308703Z'},
                'propF': {'type': 'list', 'value': ['A', 'B']},
                'propG': {'type': 'map', 'value': {'A': 'ValueA', 'B': 'ValueB'}}
            }),
            PropValueMap({
                'propA': {'type': 'string', 'value': 'sysPropA'}
            })
        )
        self.assertEqual(result, PropValueMap({
            'propA': {'type': 'string', 'value': 'propA'}, 
            'propB': {'type': 'integer', 'value': 1},
            'propC': {'type': 'float', 'value': 1.6},
            'propD': {'type': 'boolean', 'value': True},
            'propE': {'type': 'timestamp', 'value': '2020-11-23T11:49:33.308703Z'},
            'propF': {'type': 'list', 'value': ['A', 'B']},
            'propG': {'type': 'map', 'value': {'A': 'ValueA', 'B': 'ValueB'}},
            'system_propA': {'type': 'string', 'value': 'sysPropA'}
        }))

    def test_merge_keys(self):
        merger = PropertiesMerger()
        result = merger.merge(
            PropValueMap({
                'propA': {'type': 'key', 'privateKey': 'private', 'publicKey': 'public', 'keyName': 'SomeKey'}, 
                'propB': {'type': 'string', 'value': 'propB'}
            }),
            PropValueMap({
                'propA': {'type': 'string', 'value': 'sysPropA'}
            })
        )
        self.assertEqual(result, PropValueMap({
            'propA': {'type': 'key', 'privateKey': 'private', 'publicKey': 'public', 'keyName': 'SomeKey'},
            'propB': {'type': 'string', 'value': 'propB'},
            'system_propA': {'type': 'string', 'value': 'sysPropA'}
        }))

class TestStackNameCreator(unittest.TestCase):

    def test_create(self):
        creator = StackNameCreator()
        uid = str(uuid.uuid4())
        name = creator.create(uid, 'ResourceA')
        self.assertEqual(name, 'ResourceA.{0}'.format(uid))

    def test_create_ensures_starts_with_letter(self):
        creator = StackNameCreator()
        uid = str(uuid.uuid4())
        name = creator.create(uid, '123ResourceA')
        self.assertEqual(name, 's123ResourceA.{0}'.format(uid))

    def test_create_ensures_length(self):
        creator = StackNameCreator()
        uid = str(uuid.uuid4())
        length_of_uid = len(uid)
        lots_of_As = 'A' * (258-length_of_uid)
        self.assertEqual(len(lots_of_As)+length_of_uid, 258)
        expected_As = 'A' * (254-length_of_uid)
        name = creator.create(uid, lots_of_As)
        self.assertEqual(len(name), 255)
        self.assertEqual(name, '{0}.{1}'.format(expected_As, uid))

    def test_create_ensures_length_and_starts_with_letter(self):
        creator = StackNameCreator()
        uid = str(uuid.uuid4())
        length_of_uid = len(uid)
        lots_of_Ones = '1' * (258-length_of_uid)
        self.assertEqual(len(lots_of_Ones)+length_of_uid, 258)
        expected_Ones = '1' * (253-length_of_uid)
        name = creator.create(uid, lots_of_Ones)
        self.assertEqual(len(name), 255)
        self.assertEqual(name, 's{0}.{1}'.format(expected_Ones, uid))

    def test_create_removes_special_chars(self):
        creator = StackNameCreator()
        uid = str(uuid.uuid4())
        str_with_special_chars = 'A$ %!--__b.c#@'
        name = creator.create(uid, str_with_special_chars)
        self.assertEqual(name, 'A--__b.c.{0}'.format(uid))

class TestResourceDriverHandler(unittest.TestCase):

    def setUp(self):
        self.__create_mock_driver_files()
        self.resource_driver_config = AdditionalResourceDriverProperties()
        self.adopt_config = AdoptProperties()
        self.mock_heat_input_utils = MagicMock()
        self.mock_heat_input_utils.filter_used_properties.return_value = {'propA': 'valueA'}
        self.mock_heat_input_utils.filter_password_from_dictionary.return_value =  self.heat_template
        self.mock_heat_driver = MagicMock()
        self.mock_os_location = MagicMock(heat_driver=self.mock_heat_driver)
        self.mock_os_location.get_heat_input_util.return_value = self.mock_heat_input_utils
        self.mock_location_translator = MagicMock()
        self.mock_location_translator.from_deployment_location.return_value = self.mock_os_location
        self.mock_heat_translator = MagicMock()
        self.mock_heat_translator.generate_heat_template.return_value = '''
                                                                        parameters:
                                                                          propA:
                                                                            type: string
                                                                        '''
        self.mock_tosca_discover_service = MagicMock()
        self.system_properties = self.__system_properties()
        self.resource_properties = self.__resource_properties()
        self.tosca_request_properties = self.__tosca_request_properties()
        self.deployment_location = self.__deployment_location()
        self.created_associated_topology = self.__created_associated_topology()
        self.created_adopted_topology = self.__created_adopted_topology()        

    def tearDown(self):
        if os.path.exists(self.heat_driver_files.root_path):
            shutil.rmtree(self.heat_driver_files.root_path)
        if os.path.exists(self.tosca_driver_files.root_path):
            shutil.rmtree(self.tosca_driver_files.root_path)

    def __create_mock_driver_files(self):
        heat_driver_files_path = tempfile.mkdtemp()
        self.heat_template = 'heat_template'
        with open(os.path.join(heat_driver_files_path, 'heat.yaml'), 'w') as f:
            f.write(self.heat_template)
        tosca_driver_files_path = tempfile.mkdtemp()
        self.tosca_template = 'tosca_template'
        self.tosca_template_path = os.path.join(tosca_driver_files_path, 'tosca.yaml')
        with open(self.tosca_template_path, 'w') as f:
            f.write(self.tosca_template)
        self.discover_template = 'discover_template'
        with open(os.path.join(tosca_driver_files_path, 'discover.yaml'), 'w') as f:
            f.write(self.discover_template)
        self.heat_driver_files = DirectoryTree(heat_driver_files_path)
        self.tosca_driver_files = DirectoryTree(tosca_driver_files_path)
        
    def __system_properties(self):
        props = {}
        props['resourceId'] = '123'
        props['resourceName'] = 'TestResource'
        return PropValueMap(props)

    def __resource_properties(self):
        props = {}
        props['propA'] = {'type': 'string', 'value': 'valueA'}
        props['propB'] = {'type': 'string', 'value': 'valueB'}
        return PropValueMap(props)

    def __tosca_request_properties(self):
        props = {'template-type': {'type': 'string', 'value': 'TOSCA'}}
        return PropValueMap(props)

    def __deployment_location(self):
        return {'name': 'mock_location'}

    def __created_associated_topology(self):
        associated_topology = AssociatedTopology()
        associated_topology.add_entry('InfrastructureStack', '1', 'Openstack')
        return associated_topology

    def __created_adopted_topology(self):
        associated_topology = AssociatedTopology()
        associated_topology.add_entry('555', '555', 'Openstack')
        return associated_topology

    def assert_request_id(self, request_id, expected_prefix, expected_stack_id):
        self.assertTrue(request_id.startswith(expected_prefix + '::' + expected_stack_id + '::'))

    def assert_internal_resource(self, associated_topology, expected_stack_id):
        result = associated_topology.find_id(expected_stack_id)
        self.assertEqual(len(result), 1)
        self.assertIn('InfrastructureStack', result)
        self.assertEqual(result['InfrastructureStack'].element_id, expected_stack_id)
        self.assertEqual(result['InfrastructureStack'].element_type, 'Openstack')

    @patch('osvimdriver.service.resourcedriver.StackNameCreator')
    def test_create_infrastructure_uses_stack_name_creator(self, mock_stack_name_creator):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=self.adopt_config)
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        mock_stack_name_creator_inst = mock_stack_name_creator.return_value
        mock_stack_name_creator_inst.create.assert_called_once_with('123', 'TestResource')
        self.mock_heat_driver.create_stack.assert_called_once_with(mock_stack_name_creator_inst.create.return_value, self.heat_template, {'propA': 'valueA'})

    def test_create_infrastructure_with_stack_id_input(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.resource_properties['stack_id'] = {'type': 'string', 'value': 'MY_STACK_ID'}
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_internal_resource(result.associated_topology, 'MY_STACK_ID')
        self.mock_heat_translator.generate_heat_template.assert_not_called()
        self.mock_heat_driver.create_stack.assert_not_called()
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.get_stack.assert_called_once_with('MY_STACK_ID')

    def test_create_infrastructure_with_not_found_stack_id(self):
        self.mock_heat_driver.get_stack.side_effect = StackNotFoundError('Existing stack not found')
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.resource_properties['stack_id'] = {'type': 'string', 'value': 'MY_STACK_ID'}
        with self.assertRaises(InfrastructureNotFoundError) as context:
            driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertEqual(str(context.exception), 'Existing stack not found')

    def test_create_infrastructure_with_stack_id_as_none(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.resource_properties['stack_id'] = {'type': 'string', 'value': None}
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_internal_resource(result.associated_topology, '1')
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.heat_template, {'propA': 'valueA'})
        self.mock_heat_driver.get_stack.assert_not_called()

    def test_create_infrastructure_with_stack_id_empty(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.resource_properties['stack_id'] = {'type': 'string', 'value': '  '}
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_internal_resource(result.associated_topology, '1')
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.heat_template, {'propA': 'valueA'})
        self.mock_heat_driver.get_stack.assert_not_called()

    def test_create_infrastructure(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_internal_resource(result.associated_topology, '1')
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.heat_template, {'propA': 'valueA'})

    def test_create_infrastructure_includes_heat_files(self):
        files_path = os.path.join(self.heat_driver_files.root_path, 'files')
        os.makedirs(files_path)
        os.makedirs(os.path.join(files_path, 'subdir'))
        with open(os.path.join(files_path, 'subdir', 'fileA.yaml'), 'w') as f:
            f.write('fileA: test')
        with open(os.path.join(files_path, 'fileB.yaml'), 'w') as f:
            f.write('fileB: test')
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        _ = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.heat_template, {'propA': 'valueA'}, files={
            os.path.join('subdir', 'fileA.yaml'): 'fileA: test',
            'fileB.yaml': 'fileB: test',
        })

    
    def test_create_infrastructure_uses_system_prop(self):
        self.mock_heat_input_utils.filter_used_properties.return_value = {'system_resourceId': '123'}
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.mock_heat_input_utils.filter_used_properties.assert_called_once_with(self.heat_template, PropValueMap({
            'propA': {'type': 'string', 'value': 'valueA'},
            'propB': {'type': 'string', 'value': 'valueB'},
            'system_resourceId': {'type': 'string', 'value': '123'},
            'system_resourceName': {'type': 'string', 'value': 'TestResource'}
        }))
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.heat_template, {'system_resourceId': '123'})

    def test_create_infrastructure_with_tosca(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Create', self.tosca_driver_files, self.system_properties, self.resource_properties, self.tosca_request_properties, AssociatedTopology(), self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_internal_resource(result.associated_topology, '1')
        self.mock_heat_translator.generate_heat_template.assert_called_once_with(self.tosca_template, template_path=self.tosca_template_path)
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.create_stack.assert_called_once_with(ANY, self.mock_heat_translator.generate_heat_template.return_value, {'propA': 'valueA'})

    def test_create_infrastructure_with_invalid_tosca_template_throws_error(self):
        self.mock_heat_translator.generate_heat_template.side_effect = ToscaValidationError('Validation error')
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InvalidDriverFilesError) as context:
            driver.execute_lifecycle('Create', self.tosca_driver_files, self.system_properties, self.resource_properties, {'template-type': 'TOSCA'}, AssociatedTopology(), self.deployment_location)
        self.assertEqual(str(context.exception), 'Validation error')

    def test_create_infrastructure_with_invalid_template_type_throws_error(self):
        request_properties = {'template-type': 'YAML'}
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InvalidDriverFilesError) as context:
            driver.execute_lifecycle('Create', self.tosca_driver_files, self.system_properties, self.resource_properties, request_properties, AssociatedTopology(), self.deployment_location)
        self.assertEqual(str(context.exception), 'Cannot create using template of type \'YAML\'. Must be one of: [\'TOSCA\', \'HEAT\']')

    def test_adopt_infrastructure(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)             
        result = driver.execute_lifecycle('Adopt', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_adopted_topology, self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)        
        self.assert_request_id(result.request_id, 'Adopt', '555')        
        self.assert_internal_resource(result.associated_topology, '555')
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)

    def test_adopt_infrastructure_with_no_associated_topology(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InvalidRequestError) as context:
            driver.execute_lifecycle('Adopt', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertEqual(str(context.exception), 'You must supply exactly one stack_id to adopt in associated_topology')

    def test_adopt_infrastructure_with_too_many_associated_topology(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)                     
        associated_topology = self.created_adopted_topology
        self.created_adopted_topology.add_entry('556', '556', 'Openstack')
        with self.assertRaises(InvalidRequestError) as context:
            driver.execute_lifecycle('Adopt', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_adopted_topology, self.deployment_location)
        self.assertEqual(str(context.exception), 'You must supply exactly one stack_id to adopt in associated_topology')

    def test_adopt_deleted_infrastructure(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '555',
            'stack_status': 'DELETE_COMPLETE'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)             
        with self.assertRaises(InvalidRequestError) as context:
            driver.execute_lifecycle('Adopt', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_adopted_topology, self.deployment_location)
        self.assertEqual(str(context.exception), 'The stack \'555\' has been deleted')

    def test_delete_infrastructure(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Delete', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_associated_topology, self.deployment_location)
        self.assertIsInstance(result, LifecycleExecuteResponse)
        self.assert_request_id(result.request_id, 'Delete', '1')
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.delete_stack.assert_called_once_with('1',result.request_id)

    def test_delete_infrastructure_stack_not_found(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.mock_heat_driver.delete_stack.side_effect = StackNotFoundError('Not found')
        result = driver.execute_lifecycle('Delete', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_associated_topology, self.deployment_location)
        self.assert_request_id(result.request_id, 'Delete', '1')
    
    def test_execute_lifecycle_on_unsupported_lifecycle_raises_error(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InvalidRequestError) as context:
            driver.execute_lifecycle('Start', self.heat_driver_files, self.system_properties, self.resource_properties, {}, self.created_associated_topology, self.deployment_location)
        self.assertEqual(str(context.exception), 'Openstack driver only supports Create, Adopt and Delete transitions, not Start')

    def test_get_lifecycle_execution_for_delete_stack_not_found(self):
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        self.mock_heat_driver.get_stack.side_effect = StackNotFoundError('Not found')
        execution = driver.get_lifecycle_execution('Delete::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Delete::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_executions_requests_stack(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_IN_PROGRESS'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_heat_driver.get_stack.assert_called_once_with('1',execution.request_id)

    def test_get_lifecycle_execution_create_in_progress(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_IN_PROGRESS'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'IN_PROGRESS')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_create_complete(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_COMPLETE',
            'outputs': [
                {'output_key': 'outputA', 'output_value': 'valueA'},
                {'output_key': 'outputB', 'output_value': 123}
            ]
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, {'outputA': 'valueA', 'outputB': 123})
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_adopt_complete(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_COMPLETE',
            'outputs': [
                {'output_key': 'outputA', 'output_value': 'valueA'},
                {'output_key': 'outputB', 'output_value': 'valueB'}
            ]
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=self.adopt_config)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, {'outputA': 'valueA', 'outputB': 'valueB'})
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_adopt_resumed(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'RESUME_COMPLETE',
            'outputs': [
                {'output_key': 'outputA', 'output_value': 'valueA'},
                {'output_key': 'outputB', 'output_value': 'valueB'}
            ]
        }
        # don't pass adopt_config to check defaults are used 
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, {'outputA': 'valueA', 'outputB': 'valueB'})
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_adopt_suspended(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'SUSPEND_COMPLETE',
            'stack_status_reason': 'SUSPEND_COMPLETE'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=self.adopt_config)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'FAILED')        
        self.assertEqual(str(execution.failure_details), 'failure_code: INFRASTRUCTURE_ERROR description: Adopt failed: cannot adopt stack with status SUSPEND_COMPLETE')

    def test_get_lifecycle_execution_adopt_skip_status_check(self):
        # here we generate a stack status of suspended, but will still import, becuase the skip status check will be set
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'SUSPEND_COMPLETE',
            'stack_status_reason': 'SUSPEND_COMPLETE'
        }
        adopt_conf=self.adopt_config
        adopt_conf.skip_status_check=True
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=adopt_conf)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')      
  
    def test_get_lifecycle_execution_adopt_additionally_configured_status(self):
        # here we generate a stack status of snapshot_complete, but will still import, becuase we'll add it to the list, as if configured
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'SNAPSHOT_COMPLETE',
            'stack_status_reason': 'SNAPSHOT_COMPLETE'
        }
        adopt_conf=self.adopt_config
        adopt_conf.adoptable_status_values.append('SNAPSHOT_COMPLETE')     
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=adopt_conf)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')

    def test_get_lifecycle_execution_create_complete_no_outputs(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_COMPLETE',
            'outputs': []
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_create_complete_no_outputs_key(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_COMPLETE'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_create_failed(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_FAILED',
            'stack_status_reason': 'For the test'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual(execution.failure_details.failure_code, 'INFRASTRUCTURE_ERROR')
        self.assertEqual(execution.failure_details.description, 'For the test')
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_adopt_failed(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'ADOPT_FAILED',
            'stack_status_reason': 'For the test'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service, adopt_config=self.adopt_config)
        execution = driver.get_lifecycle_execution('Adopt::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Adopt::1::request123')
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual(execution.failure_details.failure_code, 'INFRASTRUCTURE_ERROR')
        self.assertEqual(execution.failure_details.description, 'Adopt failed: cannot adopt stack with status ADOPT_FAILED')
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_create_failed_with_no_reason(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'CREATE_FAILED'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Create::1::request123')
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual(execution.failure_details.failure_code, 'INFRASTRUCTURE_ERROR')
        self.assertEqual(execution.failure_details.description, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_delete_in_progress(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'DELETE_IN_PROGRESS'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Delete::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Delete::1::request123')
        self.assertEqual(execution.status, 'IN_PROGRESS')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_delete_complete(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'DELETE_COMPLETE'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Delete::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Delete::1::request123')
        self.assertEqual(execution.status, 'COMPLETE')
        self.assertEqual(execution.failure_details, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_delete_failed(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'DELETE_FAILED',
            'stack_status_reason': 'For the test'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Delete::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Delete::1::request123')
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual(execution.failure_details.failure_code, 'INFRASTRUCTURE_ERROR')
        self.assertEqual(execution.failure_details.description, 'For the test')
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_delete_failed_with_no_reason(self):
        self.mock_heat_driver.get_stack.return_value = {
            'id': '1',
            'stack_status': 'DELETE_FAILED'
        }
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        execution = driver.get_lifecycle_execution('Delete::1::request123', self.deployment_location)
        self.assertIsInstance(execution, LifecycleExecution)
        self.assertEqual(execution.request_id, 'Delete::1::request123')
        self.assertEqual(execution.status, 'FAILED')
        self.assertEqual(execution.failure_details.failure_code, 'INFRASTRUCTURE_ERROR')
        self.assertEqual(execution.failure_details.description, None)
        self.assertEqual(execution.outputs, None)
        self.assertEqual(execution.associated_topology, None)

    def test_get_lifecycle_execution_error_when_not_found(self):
        self.mock_heat_driver.get_stack.side_effect = StackNotFoundError('Not found')
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InfrastructureNotFoundError) as context:
            driver.get_lifecycle_execution('Create::1::request123', self.deployment_location)
        self.assertEqual(str(context.exception), 'Not found')

    def test_find_reference(self):
        self.mock_tosca_discover_service.discover.return_value = DiscoveryResult('1', {'test': '1'})
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        response = driver.find_reference('test', self.tosca_driver_files, self.deployment_location)
        self.assertIsInstance(response, FindReferenceResponse)
        self.assertIsNotNone(response.result)
        self.assertIsInstance(response.result, FindReferenceResult)
        self.assertEqual(response.result.associated_topology, None)
        self.assertEqual(response.result.outputs, {'test': '1'})
        self.mock_location_translator.from_deployment_location.assert_called_once_with(self.deployment_location)
        self.mock_tosca_discover_service.discover.assert_called_once_with(self.discover_template, self.mock_location_translator.from_deployment_location.return_value, {'instance_name': 'test'})

    def test_find_reference_returns_empty_when_not_found(self):
        self.mock_tosca_discover_service.discover.side_effect = NotDiscoveredError('Not found')
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        response = driver.find_reference('test', self.tosca_driver_files, self.deployment_location)
        self.assertIsInstance(response, FindReferenceResponse)
        self.assertIsNone(response.result)

    def test_find_reference_with_invalid_template_throws_error(self):
        self.mock_tosca_discover_service.discover.side_effect = ToscaValidationError('Validation error')
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        with self.assertRaises(InvalidDriverFilesError) as context:
            driver.find_reference('test', self.tosca_driver_files, self.deployment_location)
        self.assertEqual(str(context.exception), 'Validation error')

    def test_execute_lifecycle_removes_files(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertFalse(os.path.exists(self.heat_driver_files.root_path))

    def test_execute_lifecycle_keeps_files(self):
        self.mock_heat_driver.create_stack.return_value = '1','request1234'
        self.resource_driver_config.keep_files = True
        driver = ResourceDriverHandler(self.mock_location_translator, resource_driver_config=self.resource_driver_config, heat_translator_service=self.mock_heat_translator, tosca_discovery_service=self.mock_tosca_discover_service)
        result = driver.execute_lifecycle('Create', self.heat_driver_files, self.system_properties, self.resource_properties, {}, AssociatedTopology(), self.deployment_location)
        self.assertTrue(os.path.exists(self.heat_driver_files.root_path))

     

      
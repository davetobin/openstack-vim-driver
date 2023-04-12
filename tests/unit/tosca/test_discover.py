import uuid
from toscaparser.tosca_template import ToscaTemplate
import unittest
import os
import yaml
from unittest.mock import patch, MagicMock
from osvimdriver.service.tosca import ToscaParserService
from osvimdriver.tosca.discover import ToscaTopologySearchEngine, NetworkSearchImpl, InvalidDiscoveryToscaError, DiscoveryResult, NotDiscoveredError
from tests.unit.testutils.constants import TOSCA_TEMPLATES_PATH, TOSCA_MISSING_NODE_TEMPLATES, TOSCA_MULTIPLE_NODE_TEMPLATES, TOSCA_NOT_A_NETWORK_FILE, \
    TOSCA_DISCOVER_NETWORK_FILE, TOSCA_DISCOVER_NETWORK_WITH_INPUTS_FILE, TOSCA_DISCOVER_NETWORK_WITH_UNSUPPORTED_PROPERTY_FUNCTION_FILE, \
    TOSCA_DISCOVER_NETWORK_WITH_UNSUPPORTED_PROPERTY_FILE, TOSCA_DISCOVER_NETWORK_WITH_MUTLTIPLE_PROPERTIES_FILE, TOSCA_DISCOVER_NETWORK_WITH_ID_FILE, \
    TOSCA_DISCOVER_NETWORK_WITH_OUTPUTS_FILE, TOSCA_DISCOVER_NETWORK_WITH_FIXED_OUTPUT_FILE, TOSCA_DISCOVER_NETWORK_WITH_GET_PROPERTY_OUTPUT_FILE, \
    TOSCA_DISCOVER_NETWORK_WITH_OUTPUT_TO_OTHER_NODE_FILE, TOSCA_DISCOVER_NETWORK_WITH_GET_INPUT_OUTPUT_FILE, \
    TOSCA_DISCOVER_NETWORK_WITH_CONCAT_OUTPUT_FILE, TOSCA_DISCOVER_NETWORK_WITH_TOKEN_OUTPUT_FILE, TOSCA_DISCOVER_NETWORK_WITH_GET_OPERATION_OUTPUT_FILE, \
    TOSCA_DISCOVER_NETWORK_FULL_ATTRIBUTES_SUPPORT_FILE
from neutronclient.common import exceptions as neutronexceptions


class TestToscaTopologySearchEngine(unittest.TestCase):

    def test_init_without_template_fails(self):
        with self.assertRaises(ValueError) as context:
            ToscaTopologySearchEngine(None, MagicMock())
        self.assertEqual(str(context.exception), 'Must provide tosca_template parameter')

    def test_init_without_location_fails(self):
        with self.assertRaises(ValueError) as context:
            ToscaTopologySearchEngine(MagicMock(), None)
        self.assertEqual(str(context.exception), 'Must provide openstack_location parameter')

    @patch('osvimdriver.tosca.discover.NetworkSearchImpl')
    def test_discover(self, mock_network_search_impl_init):
        template = MagicMock()
        location = MagicMock()
        search_engine = ToscaTopologySearchEngine(template, location)
        result = search_engine.discover()
        mock_network_search_impl_init.assert_called_once_with(location)
        mock_network_search_impl_init.return_value.discover.assert_called_once_with(template)
        self.assertEqual(result, mock_network_search_impl_init.return_value.discover.return_value)


tosca_templates_dir = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, TOSCA_TEMPLATES_PATH)
missing_node_templates_tosca_file = os.path.join(tosca_templates_dir, TOSCA_MISSING_NODE_TEMPLATES)
multiple_node_templates_tosca_file = os.path.join(tosca_templates_dir, TOSCA_MULTIPLE_NODE_TEMPLATES)
not_a_network_tosca_file = os.path.join(tosca_templates_dir, TOSCA_NOT_A_NETWORK_FILE)
discover_network_tosca_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_FILE)
discover_network_with_inputs_tosca_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_INPUTS_FILE)
discover_network_with_unsupported_property_function_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_UNSUPPORTED_PROPERTY_FUNCTION_FILE)
discover_network_with_unsupported_property_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_UNSUPPORTED_PROPERTY_FILE)
discover_network_with_multiple_properties_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_MUTLTIPLE_PROPERTIES_FILE)
discover_network_with_id_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_ID_FILE)
discover_network_with_outputs_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_OUTPUTS_FILE)
discover_network_with_fixed_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_FIXED_OUTPUT_FILE)
discover_network_with_get_property_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_GET_PROPERTY_OUTPUT_FILE)
discover_network_with_output_to_other_node_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_OUTPUT_TO_OTHER_NODE_FILE)
discover_network_with_get_input_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_GET_INPUT_OUTPUT_FILE)
discover_network_with_concat_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_CONCAT_OUTPUT_FILE)
discover_network_with_token_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_TOKEN_OUTPUT_FILE)
discover_network_with_get_operation_output_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_WITH_GET_OPERATION_OUTPUT_FILE)
discover_network_full_attributes_support_file = os.path.join(tosca_templates_dir, TOSCA_DISCOVER_NETWORK_FULL_ATTRIBUTES_SUPPORT_FILE)


class TestNetworkSearchImpl(unittest.TestCase):

    def setUp(self):
        self.mock_neutron_driver = MagicMock()
        self.mock_openstack_location = MagicMock(neutron_driver=self.mock_neutron_driver)

    def __get_template(self, file_name, inputs=None):
        with open(file_name, 'r') as tosca_reader:
            tosca_template_str = tosca_reader.read()
        return ToscaParserService().parse_tosca_str(tosca_template_str, inputs)

    def __configure_mock_neutron_driver_with_not_found(self, network_name):
        self.mock_neutron_driver.get_network_by_name.side_effect = neutronexceptions.NotFound(message='Unable to find network with name \'{0}\''.format(network_name))

    def __configure_mock_neutron_driver_with_network(self, network_name):
        self.test_network = {
            'id': network_name,
            'name': network_name
        }
        self.mock_neutron_driver.get_network_by_name.return_value = self.test_network

    def __configure_mock_neutron_driver_with_network_on_id(self, network_id, network_name=None):
        if network_name == None:
            network_name = network_id
        self.test_network = {
            'id': network_id,
            'name': network_name
        }
        self.mock_neutron_driver.get_network_by_id.return_value = self.test_network

    def test_init_without_location_fails(self):
        with self.assertRaises(ValueError) as context:
            search_impl = NetworkSearchImpl(None)
        self.assertEqual(str(context.exception), 'Must provide openstack_location parameter')

    def test_discover_without_template_fails(self):
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(ValueError) as context:
            search_impl.discover(None)
        self.assertEqual(str(context.exception), 'Must provide tosca_template parameter')

    def test_discover_no_node_templates_fails(self):
        tosca_template = self.__get_template(missing_node_templates_tosca_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'tosca_template features no node_templates, so there is nothing to discover')

    def test_discover_multiple_nodes_fails(self):
        tosca_template = self.__get_template(multiple_node_templates_tosca_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'tosca_template for topology discovery expected to feature only a single node template')

    def test_discover_non_network_type_fails(self):
        tosca_template = self.__get_template(not_a_network_tosca_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'Cannot discover nodes of type: tosca.nodes.Custom')

    @patch('osvimdriver.tosca.discover.uuid4')
    def test_discover_network(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_tosca_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.mock_neutron_driver.get_network_by_name.assert_called_once_with('TestNetwork','request1234')
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, 'TestNetwork')
        self.assertEqual(search_result.outputs, {})

    @patch('osvimdriver.tosca.discover.uuid4')
    def test_discover_network_by_id(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network_on_id('1234','TestNetwork')
        tosca_template = self.__get_template(discover_network_with_id_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.mock_neutron_driver.get_network_by_id.assert_called_once_with('1234','request1234')
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, '1234')
        self.assertEqual(search_result.outputs, {})

    @patch('osvimdriver.tosca.discover.uuid4')
    def test_discover_network_with_input_property(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network('NetworkA')
        tosca_template = self.__get_template(discover_network_with_inputs_tosca_file, {'network_name': 'NetworkA'})
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, 'NetworkA')
        self.assertEqual(search_result.outputs, {})
        self.mock_neutron_driver.get_network_by_name.assert_called_once_with('NetworkA','request1234')

    def test_discover_network_with_unsupported_property_function_fails(self):
        tosca_template = self.__get_template(discover_network_with_unsupported_property_function_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'Resolving function of type \'GetAttribute\' is not supported through discovery')

    def test_discover_by_unsupported_property_fails(self):
        tosca_template = self.__get_template(discover_network_with_unsupported_property_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'tosca.nodes.network.Network nodes can only be found with a single \'network_name\' or \'network_id\' property but \'ip_version\' was set instead')

    def test_discover_by_multiple_property_fails(self):
        tosca_template = self.__get_template(discover_network_with_multiple_properties_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'tosca.nodes.network.Network nodes can only be found with a single \'network_name\' or \'network_id\' property but multiple properties were found on the node template: [\'network_name\', \'ip_version\']')
    
    @patch('osvimdriver.tosca.discover.uuid4')
    def test_discover_network_with_outputs(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_outputs_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.mock_neutron_driver.get_network_by_name.assert_called_once_with('TestNetwork','request1234')
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, 'TestNetwork')
        self.assertEqual(search_result.outputs, {'network_name': 'TestNetwork'})

    @patch('osvimdriver.tosca.discover.uuid4')      
    def test_discover_network_with_fixed_output(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_fixed_output_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.mock_neutron_driver.get_network_by_name.assert_called_once_with('TestNetwork','request1234')
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, 'TestNetwork')
        self.assertEqual(search_result.outputs, {'found': True})

    def ignored_test_discover_with_output_to_other_node_fails(self):
        # Currently not possible as the Tosca Parser validates the output references a known node_template
        # and the NetworkSearchImpl validates that there is only one node_template
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_output_to_other_node_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Attributes can only been resolved to the single node_template named \'network\' but output \'network_name}\' references \'other_node\'')

    def test_discover_with_get_property_output_fails(self):
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_get_property_output_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Resolving output value with function \'GetProperty\' is not supported through discovery - you should use get_attribute instead')

    def test_discover_with_get_input_output_fails(self):
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_get_input_output_file, {'network_name': 'TestNetwork'})
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Resolving output value with function \'GetInput\' is not supported through discovery')

    def test_discover_with_concat_output_fails(self):
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_concat_output_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Resolving output value with function \'Concat\' is not supported through discovery')

    def test_discover_with_token_output_fails(self):
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_token_output_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Resolving output value with function \'Token\' is not supported through discovery')

    def test_discover_with_get_operation_output_fails(self):
        self.__configure_mock_neutron_driver_with_network('TestNetwork')
        tosca_template = self.__get_template(discover_network_with_get_operation_output_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(InvalidDiscoveryToscaError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception),
                         'Resolving output value with function \'GetOperationOutput\' is not supported through discovery')

    def __configure_mock_neutron_driver_with_network_and_subnets(self, network_name):
        self.test_network = {
            'id': network_name,
            'name': network_name,
            'provider:network_type': 'vxlan',
            'provider:physical_network': 'phys',
            'provider:segmentation_id': 1002,
            'subnets': ['1234', '5678']
        }
        self.test_subnet_a = {
            'id': '1234',
            'name': 'subnetA',
            'enable_dhcp': True,
            'ip_version': 4,
            'gateway_ip': '192.0.0.1',
            'cidr': '192.0.0.0/8',
            'mock_uuid4' : 'request1234',
            'allocation_pools': [
                {
                    'start': '192.0.0.2',
                    'end': '192.255.255.100'
                },
                {
                    'start': '192.255.255.150',
                    'end': '192.255.255.254'
                }
            ]
            
        }
        self.test_subnet_b = {
            'id': '5678',
            'name': 'subnetB',
            'mock_uuid4' : 'request1234',
            'enable_dhcp': False,
            'ip_version': 4,
            'gateway_ip': '10.0.0.1',
            'cidr': '10.0.0.0/8',
            'allocation_pools': [
                {
                    'start': '10.0.0.2',
                    'end': '10.255.255.100'
                },
                {
                    'start': '10.255.255.150',
                    'end': '10.255.255.254'
                }
            ]
        }
        self.mock_neutron_driver.get_network_by_name.return_value = self.test_network

        #@patch('osvimdriver.tosca.discover.uuid4')
        def mock_get_subnet_by_id(subnet_id,mock_uuid4):
            if subnet_id == '1234':
                return self.test_subnet_a
            elif subnet_id == '5678':
                return self.test_subnet_b
            else:
                raise ValueError('Not a mocked subnet: {0}'.formt(subnet_id))
        self.mock_neutron_driver.get_subnet_by_id.side_effect = mock_get_subnet_by_id

    @patch('osvimdriver.tosca.discover.uuid4')
    def test_discover_full_attribute_support(self,mock_uuid4):
        mock_uuid4.return_value = 'request1234'
        self.__configure_mock_neutron_driver_with_network_and_subnets('TestNetwork')
        tosca_template = self.__get_template(discover_network_full_attributes_support_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        search_result = search_impl.discover(tosca_template)
        self.mock_neutron_driver.get_network_by_name.assert_called_once_with('TestNetwork','request1234')
        self.assertIsInstance(search_result, DiscoveryResult)
        self.assertEqual(search_result.discover_id, 'TestNetwork')
        self.assertEqual(search_result.outputs, {
            'ip_version': self.test_subnet_a['ip_version'],
            'cidr': self.test_subnet_a['cidr'],
            'start_ip': self.test_subnet_a['allocation_pools'][0]['start'],
            'end_ip': self.test_subnet_a['allocation_pools'][0]['end'],
            'gateway_ip': self.test_subnet_a['gateway_ip'],
            'network_id': self.test_network['id'],
            'network_name': self.test_network['name'],
            'segmentation_id': self.test_network['provider:segmentation_id'],
            'network_type': self.test_network['provider:network_type'],
            'physical_network': self.test_network['provider:physical_network'],
            'dhcp_enabled': self.test_subnet_a['enable_dhcp']
        })

    def test_discover_not_found_raises_exception(self):
        self.__configure_mock_neutron_driver_with_not_found('TestNetwork')
        tosca_template = self.__get_template(discover_network_tosca_file)
        search_impl = NetworkSearchImpl(self.mock_openstack_location)
        with self.assertRaises(NotDiscoveredError) as context:
            search_impl.discover(tosca_template)
        self.assertEqual(str(context.exception), 'Cannot find tosca.nodes.network.Network with search value: TestNetwork')
        

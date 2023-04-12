
from uuid import uuid4
from toscaparser.functions import GetInput, GetAttribute, GetProperty, Function
from neutronclient.common import exceptions as neutronexceptions


class ToscaTopologySearchEngine:

    def __init__(self, tosca_template, openstack_location):
        if tosca_template is None:
            raise ValueError('Must provide tosca_template parameter')
        self.tosca_template = tosca_template
        if openstack_location is None:
            raise ValueError('Must provide openstack_location parameter')
        self.openstack_location = openstack_location

    def discover(self):
        return NetworkSearchImpl(self.openstack_location).discover(self.tosca_template)


class DiscoveryResult:

    def __init__(self, discover_id, outputs={}):
        self.discover_id = discover_id
        self.outputs = outputs

class NotDiscoveredError(Exception):
    pass

class NetworkSearchImpl:

    def __init__(self, openstack_location):
        if openstack_location is None:
            raise ValueError('Must provide openstack_location parameter')
        self.openstack_location = openstack_location

    def discover(self, tosca_template):
        if tosca_template is None:
            raise ValueError('Must provide tosca_template parameter')
        target_node_template = self.__find_single_node_template(tosca_template)
        network = self.__find_network(target_node_template)
        return self.__populate_result(network, target_node_template, tosca_template)

    def __find_single_node_template(self, tosca_template):
        if not hasattr(tosca_template, 'nodetemplates'):
            raise InvalidDiscoveryToscaError('tosca_template features no node_templates, so there is nothing to discover')
        node_templates = tosca_template.nodetemplates
        if node_templates is None or len(node_templates) == 0:
            raise InvalidDiscoveryToscaError('tosca_template features no node_templates, so there is nothing to discover')
        if len(node_templates) != 1:
            raise InvalidDiscoveryToscaError('tosca_template for topology discovery expected to feature only a single node template')
        single_node_template = node_templates[0]
        if not hasattr(single_node_template, 'type_definition'):
            raise InvalidDiscoveryToscaError('Could not determine node type as type definition not present on parsed node: {0}'.format(single_node_template.name))
        if not hasattr(single_node_template.type_definition, 'type'):
            raise InvalidDiscoveryToscaError('Could not determine node type as type not present on parsed node: {0}'.format(single_node_template.name))
        single_node_type = single_node_template.type_definition.type
        if single_node_type not in NetworkTranslator.TOSCA.TYPES:
            is_valid_type = False
            next_type = single_node_template.type_definition.parent_type
            while next_type != None:
                if next_type.type in NetworkTranslator.TOSCA.TYPES:
                    is_valid_type = True
                    break
                else:
                    next_type = next_type.parent_type
            if not is_valid_type:
                raise InvalidDiscoveryToscaError('Cannot discover nodes of type: {0}'.format(single_node_type))
        return single_node_template

    def __resolve_function_on_property(self, node_template, property_template):
        if isinstance(property_template, GetInput):
            return property_template.result()
        else:
            raise InvalidDiscoveryToscaError('Resolving function of type \'{0}\' is not supported through discovery'.format(property_template.__class__.__name__))

    def __find_network(self, network_node_template):
        # Must get properties for validation this way, to avoid the defaults being added for other properties
        properties_for_validation = network_node_template.type_definition.get_value(network_node_template.PROPERTIES, network_node_template.entity_tpl)
        if len(properties_for_validation) != 1:
            raise InvalidDiscoveryToscaError('{0} nodes can only be found with a single \'{1}\' or \'{2}\' property but multiple properties were found on the node template: {3}'.format(
                network_node_template.type_definition.type, NetworkTranslator.TOSCA.PROPS.NAME, NetworkTranslator.TOSCA.PROPS.ID, list(properties_for_validation.keys())))
        single_property_key = list(properties_for_validation.keys())[0]
        if single_property_key != NetworkTranslator.TOSCA.PROPS.NAME and single_property_key != NetworkTranslator.TOSCA.PROPS.ID:
            raise InvalidDiscoveryToscaError('{0} nodes can only be found with a single \'{1}\' or \'{2}\' property but \'{3}\' was set instead'.format(
                network_node_template.type_definition.type, NetworkTranslator.TOSCA.PROPS.NAME, NetworkTranslator.TOSCA.PROPS.ID, single_property_key))
        neutron_driver = self.openstack_location.neutron_driver
        properties = network_node_template.get_properties()
        target_property_value = properties[single_property_key].value
        if isinstance(target_property_value, Function):
            target_search_value = self.__resolve_function_on_property(network_node_template, target_property_value)
        else:
            target_search_value = target_property_value
        try:
            driver_request_id  = str(uuid4())
            if single_property_key == NetworkTranslator.TOSCA.PROPS.ID:
                network = neutron_driver.get_network_by_id(target_search_value,driver_request_id)         
            else:
                network = neutron_driver.get_network_by_name(target_search_value,driver_request_id)   
            return network
        except neutronexceptions.NotFound as e:
            raise NotDiscoveredError('Cannot find {0} with search value: {1}'.format(network_node_template.type_definition.type, target_search_value)) from e

    def __populate_result(self, network, node_template, tosca_template):
        discover_id = network['id']
        outputs = self.__gather_network_outputs(network, node_template, tosca_template.outputs)
        return DiscoveryResult(discover_id, outputs)

    def __gather_network_outputs(self, network, network_node_template, outputs):
        output_results = {}
        for output in outputs:
            output_name = output.name
            output_unresolved_value = output.value
            if isinstance(output_unresolved_value, Function):
                output_value = self.__resolve_functions_on_output(network, network_node_template, output, output_unresolved_value)
            else:
                if type(output_unresolved_value) is dict:
                    self.__validate_output_value_is_not_unsupported_function(output_unresolved_value)
                output_value = output_unresolved_value
            output_results[output_name] = output_value
        return output_results

    def __validate_output_value_is_not_unsupported_function(self, output_value):
        # May seem like a duplicate of the errors thrown by __resolve_functions_on_output
        # However, the Tosca Parser in some cases will ignore certain unsupported output functions and parse them as dicts
        # So this method catches those, by validating the dictionary value on the output
        # Error messages use slightly different language to those in __resolve_functions_on_output so we can differentiate them in logs
        if 'get_property' in output_value:
            raise InvalidDiscoveryToscaError(
                'Resolving output value with function \'GetProperty\' is not supported through discovery - you should use get_attribute instead')
        elif 'get_input' in output_value:
            raise InvalidDiscoveryToscaError(
                'Resolving output value with function \'GetInput\' is not supported through discovery')
        elif 'get_operation_output' in output_value:
            raise InvalidDiscoveryToscaError(
                'Resolving output value with function \'GetOperationOutput\' is not supported through discovery')
        elif 'concat' in output_value:
            raise InvalidDiscoveryToscaError(
                'Resolving output value with function \'Concat\' is not supported through discovery')
        elif 'token' in output_value:
            raise InvalidDiscoveryToscaError(
                'Resolving output value with function \'Token\' is not supported through discovery')

    def __resolve_functions_on_output(self, node, node_template, output, output_function):
        if isinstance(output_function, GetAttribute):
            output_args = output_function.args
            if len(output_args) != 2:
                raise InvalidDiscoveryToscaError('Expected two arguments to be provided to get_attribute function on output: {0}'.format(output.name))
            target_node_name = output_args[0]
            target_attr = output_args[1]
            if target_node_name != node_template.name:
                raise InvalidDiscoveryToscaError('Attributes can only been resolved to the single node_template named \'{0}\' but output \'{1}\' references \'{2}\''.format(
                    node_template.name, output.name, target_node_name))
            return NetworkTranslator(self.openstack_location).resolve_tosca_attribute(node, target_attr)
        elif isinstance(output_function, GetProperty):
            raise InvalidDiscoveryToscaError(
                'Resolving output function of type \'{0}\' is not supported through discovery - you should use get_attribute instead'.format(output_function.__class__.__name__))
        else:
            raise InvalidDiscoveryToscaError('Resolving output function of type \'{0}\' is not supported through discovery'.format(output_function.__class__.__name__))


class InvalidDiscoveryToscaError(Exception):
    pass


class Props:

    def __init__(self, **props):
        for key, value in props.items():
            setattr(self, key, value)

    @property
    def all(self):
        return dict(self.__dict__)


class NetworkTranslator:

    TOSCA = Props(TYPES=['tosca.nodes.network.Network', 'tosca.nodes.network.NetworkWithAttr'],
                  PROPS=Props(NAME='network_name',
                              ID='network_id',
                              SEGMENTATION_ID='segmentation_id',
                              PHYSICAL_NETWORK='physical_network',
                              NETWORK_TYPE='network_type',
                              IP_VERSION='ip_version',
                              CIDR='cidr',
                              START_IP='start_ip',
                              END_IP='end_ip',
                              GATEWAY_IP='gateway_ip',
                              DHCP_ENABLED='dhcp_enabled')
                  )

    OS = Props(PROPS=Props(NAME='name',
                           ID='id',
                           SEGMENTATION_ID='provider:segmentation_id',
                           PHYSICAL_NETWORK='provider:physical_network',
                           NETWORK_TYPE='provider:network_type',
                           SUBNETS='subnets')
               )

    def __init__(self, openstack_location):
        if openstack_location is None:
            raise ValueError('Must provide openstack_location parameter')
        self.openstack_location = openstack_location
        self.on_subnet_props = [self.TOSCA.PROPS.IP_VERSION,
                                self.TOSCA.PROPS.CIDR,
                                self.TOSCA.PROPS.START_IP,
                                self.TOSCA.PROPS.END_IP,
                                self.TOSCA.PROPS.GATEWAY_IP,
                                self.TOSCA.PROPS.DHCP_ENABLED]

    def resolve_tosca_attribute(self, network_obj, tosca_attribute_name):
        if tosca_attribute_name == self.TOSCA.PROPS.NAME:
            return network_obj[self.OS.PROPS.NAME]
        elif tosca_attribute_name == self.TOSCA.PROPS.ID:
            return network_obj[self.OS.PROPS.ID]
        elif tosca_attribute_name == self.TOSCA.PROPS.SEGMENTATION_ID:
            return network_obj.get(self.OS.PROPS.SEGMENTATION_ID, None)
        elif tosca_attribute_name == self.TOSCA.PROPS.PHYSICAL_NETWORK:
            return network_obj.get(self.OS.PROPS.PHYSICAL_NETWORK, None)
        elif tosca_attribute_name == self.TOSCA.PROPS.NETWORK_TYPE:
            return network_obj.get(self.OS.PROPS.NETWORK_TYPE, None)
        elif tosca_attribute_name in self.on_subnet_props:
            return self.__resolve_tosca_attribute_from_subnet(network_obj, tosca_attribute_name)
        else:
            raise InvalidDiscoveryToscaError('Attribute \'{0}\' cannot be resolved to an Openstack property for a network'.format(tosca_attribute_name))

    def __resolve_tosca_attribute_from_subnet(self, network_obj, tosca_attribute_name):
        subnets = network_obj.get(self.OS.PROPS.SUBNETS, [])
        if len(subnets) == 0:
            return None
        # We currently support retrieval of values from first subnet only
        first_subnet_id = subnets[0]
        neutron_driver = self.openstack_location.neutron_driver
        driver_request_id  = str(uuid4())
        first_subnet = neutron_driver.get_subnet_by_id(first_subnet_id,driver_request_id)
        return NetworkSubnetTranslator().resolve_network_tosca_attribute(first_subnet, tosca_attribute_name)


class NetworkSubnetTranslator:

    OS = Props(PROPS=Props(NAME='name',
                           ID='id',
                           IP_VERSION='ip_version',
                           CIDR='cidr',
                           ALLOCATION_POOLS='allocation_pools',
                           GATEWAY_IP='gateway_ip',
                           DHCP_ENABLED='enable_dhcp')
               )

    def resolve_network_tosca_attribute(self, subnet_obj, tosca_attribute_name):
        if tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.IP_VERSION:
            return subnet_obj.get(self.OS.PROPS.IP_VERSION, None)
        elif tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.CIDR:
            return subnet_obj.get(self.OS.PROPS.CIDR, None)
        elif tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.START_IP:
            pool = self.__get_first_allocation_pool(subnet_obj)
            return None if pool is None else pool.get('start', None)
        elif tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.END_IP:
            pool = self.__get_first_allocation_pool(subnet_obj)
            return None if pool is None else pool.get('end', None)
        elif tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.GATEWAY_IP:
            return subnet_obj.get(self.OS.PROPS.GATEWAY_IP, None)
        elif tosca_attribute_name == NetworkTranslator.TOSCA.PROPS.DHCP_ENABLED:
            return subnet_obj.get(self.OS.PROPS.DHCP_ENABLED, None)
        else:
            raise InvalidDiscoveryToscaError('Attribute \'{0}\' cannot be resolved to an Openstack property for a network'.format(tosca_attribute_name))

    def __get_first_allocation_pool(self, subnet_obj):
        allocation_pools = subnet_obj.get(self.OS.PROPS.ALLOCATION_POOLS, [])
        if len(allocation_pools) == 0:
            return None
        first_allocation_pool = allocation_pools[0]
        return first_allocation_pool

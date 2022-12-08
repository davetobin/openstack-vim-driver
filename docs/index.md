# Openstack VIM Driver

This driver implements the [IBM Telco Network Cloud Manager - Orchestration](https://www.ibm.com/support/knowledgecenter/SSDSDC_1.3/welcome_page/kc_welcome-444.html) Brent Resource Driver APIs to allow infrastructure to be managed in Openstack.

The driver has been written in Python3 and can be installed with the publicly available docker image and helm chart.

# Install

The driver can installed on [Kubernetes](./k8s-install.md) using Helm.

# User Guide

The following sections explain how the driver works and the restrictions it places on the Resource package files and deployment locations.

- [Resources](./user-guide/resources.md) - using Openstack based infrastructure in your Resource
- [Property Handling](./user-guide/property-handling.md) - details how properties for a Resource are handled as inputs and outputs during requests
- [Deployment Locations](./user-guide/deployment-locations.md) - details the properties expected by this driver on a valid deployment location
- [Openstack Admin API](./user-guide/os-admin-api.md) - additional API available to check Openstack deployment locations are reachable from the driver

# Example Resources

Two example Resources have been included to demonstrate creating/deleting infrastructure and finding infrastructure:

- [Helloworld Compute](./reference/example-resources/helloworld-compute/Readme.md) - simple Resource which creates a single compute instance in Openstack (TOSCA and HEAT examples included)
- [Neutron Network](./reference/example-resources/neutron-network/Readme.md) - a Resource which supports being found with a piece of discovery infrastructure. Use this Resource as an external reference in an Assembly to link to an existing network in Openstack

# Additional Note:

If a VM instance of a stack created through Openstack VIM Driver is locked ( from the OpenStack dashboard, you can lock Compute instances ) and an uninstall of the assembly is attempted, the assembly is deleted, but the stack is not.

The DELETE stack REST api attempts to delete the stack, but it fails when it tries to delete the instance. The stack is left partially deleted in a failed_delete status.

In this case when we add lock on VM instances manually from Openstack dashboard, the orphaned stack has to be removed manually.

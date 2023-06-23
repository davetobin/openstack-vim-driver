# Resources

The Openstack driver allows you to create new or adopt pre-existing Stacks in a target Openstack as part of a `Create` or `Adopt` lifecycle transition (then remove the Stack with `Delete`). This is done by configuring the use of the driver on Create/Adopt/Delete and by including Heat or Tosca templates in your Resource package for (for a `Create` transistion).

The driver also supports finding existing Networks in a target Openstack when attempting to find an external reference Resource (in an Assembly design).

# Resource Descriptor

Openstack driver should only be used on Create/Adopt/Delete transitions.

Example descriptor:
```
lifecycle:
  Create:
    drivers:
      openstack:
        selector:
          infrastructure-type:
            Openstack
  Adopt: 
    drivers:
      Openstack:
        selector:
          infrastructure-type:
            Openstack            
  Delete:
    drivers:
      openstack:
        selector:
          infrastructure-type:
            Openstack
```

Attempts to use the driver on other transitions will result in an error.

**Note:** it's rare you need to do this but if you do not onboard the Openstack driver with type `openstack` then this value must be renamed to your chosen type.

You may also use the driver when finding an external reference:

```
queries:
  drivers:
    openstack:
      selector:
        infrastructure-type:
          Openstack
```

## Adoptable Stack States
If adopting a pre existing Openstack stack via the `Adopt` lifecycle transistion, the stack must be in one of the following states or the adopt will fail:
```
['CREATE_COMPLETE','ADOPT_COMPLETE','RESUME_COMPLETE','CHECK_COMPLETE','UPDATE_COMPLETE','SNAPSHOT_COMPLETE'] 
```

To configure additional states or bypass the status check completely, you can work with the settings in the `values.yaml` in the helm charts under `app.config.override.adopt`. It is not recommended to set `skip_status_check` to `True` unless it is a test environment. Other potential states are listed in the comments above the `adoptable_status_values` setting:

```yaml
      adopt:
        # Flag to override status check and allow adoption of a stack in any status
        skip_status_check: False
        # List of openstack stack status considered OK to adopt: 
        # Potential Values: 
        # CREATE_COMPLETE,ADOPT_COMPLETE,RESUME_COMPLETE,CHECK_COMPLETE,UPDATE_COMPLETE,SNAPSHOT_COMPLETE,INIT_COMPLETE,ROLLBACK_COMPLETE
        adoptable_status_values: ['CREATE_COMPLETE','ADOPT_COMPLETE','RESUME_COMPLETE','CHECK_COMPLETE','UPDATE_COMPLETE','SNAPSHOT_COMPLETE']  

```

# Resource Packages

A Resource using Openstack infrastructure must include either TOSCA or Heat templates in the `Lifecycle` directory of the package:

```
Lifecycle/
  openstack/
    heat.yaml
    tosca.yaml
    discover.yaml
```

**Note:** it's rare you need to do this but if you do not onboard the Openstack driver with type `openstack` then the directory above must be renamed to your chosen type. 

Infrastructure Templates are text files which describe infrastructure and can be of any type supported by this driver. Currently the Openstack VIM driver supports two template types, however only one of them may be used to find references to externally managed infrastructure:

| Template Type | Execute Lifecycle (Create Infrastructure) | Find References |
| --- | --- | --- |
| TOSCA | Y | Y |
| HEAT | Y | N |

Heat is generally easier to use as Tosca requires translation, so it's behaviour depends on whether the types used can be translated or not.

## Heat Support

The Openstack VIM driver uses the Heat API to create infrastructure, which means any template supported by the version of Heat on your Openstack environment will work fine.

We recommend reading through the Openstack [Template Guide](https://docs.openstack.org/heat/train/template_guide/) to learn about the Heat template syntax.

To use Heat, add a template to your Resource package with the name `heat.yaml` or `heat.yml`:

```
Lifecycle/
  openstack/
    heat.yaml
```

### Multiple Heat Files

In Heat you may reference additional files in a few ways: 

```
# Example 1
apache_server:
  type: "OS::Nova::Server"
  properties: 
    user_data: { "get_file": "user_data.conf" }

# Example 2
ap_router: 
    type: apache/router.yaml
```

To reference files in this way, they must be included in a `files` directory:

```
Lifecycle/
  openstack/
    files/
      apache/
        router.yaml
      user_data.conf
    heat.yaml
```

Each file in this directory is available using the path relative from the root `heat.yaml` file. 

For example, with the following file structure:

```
Lifecycle/
  openstack/
    files/
      core/
        resources.yaml
        nested-core/
          more-resources.yaml
      top-level-resources.yaml
    heat.yaml
```

The following paths may be used in a Heat template (examples shown with `type` but can be used on `get_file` also):

```
resources:
  core: 
    type: core/resources.yaml

  nested-core:
    type: core/nested-core/more-resources.yaml

  top:
    type: top-level-resources.yaml
```

## TOSCA Support

The Openstack VIM driver can create any TOSCA types from v1.0 of the [simple profile](http://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.0/csprd02/TOSCA-Simple-Profile-YAML-v1.0-csprd02.html) that are translatable to a known Heat type. The ability to translate is determined by two aspects:

- the conversion support offered in the [heat translator](https://github.com/IBM/heat-translator/tree/accanto) library used by this driver
- additional types provided by this driver

To use TOSCA when creating infrastructure, add a template to your Resource package with the name `tosca.yaml` or `tosca.yml`:

```
Lifecycle/
  openstack/
    tosca.yaml
```

To use TOSCA when finding references to your externally managed Resource, add a template to your Resource package with the name `discover.yaml` or `discover.yml`:

```
Lifecycle/
  openstack/
    discover.yaml
```

To read more about the TOSCA types supported by this driver, see [TOSCA templates](./tosca-templates.md)

### Multiple Tosca Files

To import additional TOSCA files you must include a relative path (using `./`) in the `imports` section of your TOSCA template:

```
Lifecycle/
  openstack/
    tosca.yaml
    more-tosca.yaml
```

In tosca.yaml:
```yaml
imports:
  - ./more-tosca.yaml
```

If you forget to add `./` then an error will be raised. 

**Note:** Currently only additional `node_types` are used from this imported file. 

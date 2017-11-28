"""
Replace parts of yaml config with Python objects.
"""
import importlib
import importlib.util
import os
import yaml


class ConfigParser:
  """Parser for yaml files"""
  def __init__(self):
    self.config = None

  def parse(self, filename):
      """Parse a yaml file.
      Args:
        filename (str): Path to the yaml file to be parsed.
      Returns:
        dict: Python dict with same contents as yaml file,
              but parts replaced with objects as specified
              in parse_python_objects.
      """
      filename = os.path.normpath(os.path.expanduser(filename))
      with open(filename) as config_file:
          config_dict = yaml.load(config_file)
      # Replace parts of config_dict yaml in place
      self.parse_python_objects(config_dict)
      return config_dict

  def parse_python_objects(self, yaml_dict):
      """Recursively replace parts of yaml-style dict with python objects (in place).
      Args:
        yaml_dict: Yaml-style Python dict.
      """
      if isinstance(yaml_dict, dict):

          # Add custom replacements here
          replace_obj_from_module("_fn", yaml_dict)

          for key, value in yaml_dict.items():
            self.parse_python_objects(value)

      elif isinstance(yaml_dict, list):
        for item in yaml_dict:
          self.parse_python_objects(item)


def replace_obj_from_module(string, dict):
    """Replace string values with objects, in place.

    If a key in dict contains string, the value is replaced with
    the object described by the value, which is assumed to be in
    the form 'module.submodule.object'.

    Args:
      string (str): String to look for.
      dict (dict): Dictionary being parsed.
    """
    if any_key_contains(string, dict):
      full_keys = get_full_keys_containing(string, dict)
      for full_key in full_keys:
        module_string = ".".join(dict[full_key].split(".")[:-1])
        module = importlib.import_module(module_string)
        obj_key = dict[full_key].split(".")[-1]
        dict[full_key] = getattr(module, obj_key)


def any_key_contains(string, dict):
    for key in dict.keys():
      if string in key:
        return True
    return False


def get_full_keys_containing(string, dict):
    keys = []
    for key in dict.keys():
      if string in key:
        keys.append(key)
    return keys

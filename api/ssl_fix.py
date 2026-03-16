"""
SSL Fix: Disable SSL verification warnings and set default verify=False.
This is needed for Docker containers where CA certificates may be outdated.
Import this module before making any requests.
"""
import urllib3
import requests
from functools import wraps

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey-patch requests to default verify=False
_original_request = requests.Session.request

@wraps(_original_request)
def _patched_request(self, method, url, **kwargs):
    if 'verify' not in kwargs:
        kwargs['verify'] = False
    elif kwargs['verify'] is True:
        kwargs['verify'] = False
    return _original_request(self, method, url, **kwargs)

requests.Session.request = _patched_request

# Also patch requests.get, requests.post etc.
_original_get = requests.get
_original_post = requests.post

@wraps(_original_get)
def _patched_get(url, **kwargs):
    kwargs.setdefault('verify', False)
    if kwargs['verify'] is True:
        kwargs['verify'] = False
    return _original_get(url, **kwargs)

@wraps(_original_post)
def _patched_post(url, **kwargs):
    kwargs.setdefault('verify', False)
    if kwargs['verify'] is True:
        kwargs['verify'] = False
    return _original_post(url, **kwargs)

requests.get = _patched_get
requests.post = _patched_post

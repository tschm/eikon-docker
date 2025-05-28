# 📊 Eikon-docker

[![Test](https://github.com/tschm/eikon-docker/workflows/Test/badge.svg)](https://github.com/tschm/eikon-docker/actions/)
[![Release](https://github.com/tschm/eikon-docker/workflows/Release/badge.svg)](https://github.com/tschm/eikon-docker/actions/)

🐳 Use Refinitiv's Python Eikon Data API within a Docker container.
The host of this package has to have the Eikon desktop installed.

I use this project today as playground to test the creation
and testing of containers

## 🚀 Usage

I assume you are familiar with docker. If not, this package
has no additional benefit for you. I recommend to use

[eikon](https://pypi.org/project/eikon/)

However, if you share my love for docker you may prefer
having a somewhat cleaner setup and package all tools neatly in one
container. I have not changed the API etc.

All the Eikon commands you are familiar will continue
to work (or continue to be broken).
The difference is now that the Eikon code
lives together with its dependencies in a container. Here's a little fragment:

```python
import eikon as ek
print(ek.__version__)

import logging
import http.client

http.client.HTTPConnection.debuglevel = 1

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

if __name__ == '__main__':
    ek.set_app_key('084dd01c11d749f884ba12d60c2673697ec0fa2e')

    df = ek.get_timeseries(["MSFT.O"],
                           start_date="2016-01-01",
                           end_date="2016-01-10")
    print(df)
```

## ⚖️ License

Refinitiv has released the Python Eikon Data API using the Apache 2.0 license.
By design this package will only work if installed
within a container that is running on a host with an Eikon desktop installed.
This approach is respected within this package and
we are essentially using `host.docker.internal` to access services running
on the Windows host from within a container.

Whatever you do with this package note that neither Refinitiv
nor myself will be responsible for any damage.
Please feel free to raise an issue though.

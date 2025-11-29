from utils import *
from containers import *
from bridges import *
from datetime import datetime

x = (
    "Excellent M.Sc. degree in Computer Science, Physics or Engineering​\n"
    "Strong motivation to conduct research in generative artificial intelligence in engineering​\n"
    "Interest in multi-objective optimization and machine learning\n"
)

# create_container(name="testainer", profile="default_profile.yaml")
# print(edit_yaml())

# edit_yaml(host_id=90,vlan_id=200)
# print(datetime.now().strftime("%d-%m-%Y_%Hh-%Mm"))

# queue_rates = [100,200,300,400]

dictio = [
    {"id": 1, "name": "System A", "items": ["br0", "br1", "br2"]},
    {"id": 2, "name": "System B", "items": ['br5']},
]
save_json_file(data=dictio)
print(search_json_file(key='name', value='System B'))

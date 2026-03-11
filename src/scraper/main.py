import re
from pprint import pprint

import requests
from bs4 import BeautifulSoup

response: requests.Response = requests.get("https://pisrs.si/api/datoteke/integracije/358153123", timeout=10)
html: str = response.text

soup = BeautifulSoup(html, features="html.parser")

articles = {}

elements = soup.find("p", text=re.compile("SPLOŠNI DEL")).find_next_siblings()

elements = list(filter(lambda x: "uppercase" not in x.get("class"), elements))

index = ""
is_title = True
description = ""


for element in list(elements):
    if is_title and "clen" in element.get("class"):
        description = element.string
        is_title = False
        continue

    if not is_title and "clen" in element.get("class"):
        index = element.string
        articles[index] = {"description": description}
        is_title = True
        continue

    if articles[index].get("section") is None:
        articles[index]["section"] = [element.string]
        continue

    articles[index]["section"].append(element.string)

    pprint(articles)
    pprint(element)
    input("next: ")

pprint(articles)

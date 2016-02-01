import pickle
import os
import subprocess
import collections
import re
import requests
from lxml import etree

DOMAIN = "https://updates.jenkins-ci.org"
ROOT = DOMAIN + "/download/plugins/"
Plugin = collections.namedtuple("Plugin", "version name url sha")


def plugins():
    tree = etree.HTML(requests.get(ROOT).content)
    for x in tree.xpath("//a"):
        href = x.get("href")
        if href.startswith("?C") or href.startswith("/"):
            continue
        yield ROOT + x.get("href")


def get_cached(url):
    if not os.path.exists(".metadata-cache.pickle"):
        return None
    with open(".metadata-cache.pickle", "r") as f:
        return pickle.load(f).get(url)

def set_cached(url, plugin):
    if not os.path.exists(".metadata-cache.pickle"):
        x = dict()
    else:
        with open(".metadata-cache.pickle", "r") as f:
            x = pickle.load(f)
    with open(".metadata-cache.pickle", "w") as f:
        x[url] = plugin
        pickle.dump(x, f, -1)

def versions(url):
    tree = etree.HTML(requests.get(url).content)
    for x in tree.xpath("//a"):
        if not x.get("href").endswith(".hpi"):
            continue

        # Only keep latest version for testing for now
        version = x.get("href").split("/")[-2]
        if version == "latest":
            continue

        fetch_url = DOMAIN + x.get("href")
        if get_cached(fetch_url) is not None:
            yield get_cached(fetch_url)
            continue

        try:
            sha = subprocess.check_output(["nix-prefetch-url", fetch_url]).strip()
        except subprocess.CalledProcessError:
            yield Plugin(version, url.split("/")[-2], fetch_url, "BROKEN (might be 404)")
            continue
        plugin = Plugin(version, url.split("/")[-2], fetch_url, sha)
        set_cached(fetch_url, plugin)
        yield plugin


TEMPLATE = """\
  "{name}-{version}" = mkJenkinsPlugin {{
    name = "{name}-{version}";
    src = fetchurl {{
      url = "{url}";
      sha256 = "{sha}";
    }};
  }};
"""

HEADER = """\
{ stdenv, fetchurl }:
let mkJenkinsPlugin = { name, src }: stdenv.mkDerivation {
  name = name;
  src = src;
  phases = "installPhase";
  installPhase = ''
    mkdir $out
    cp $src $out
  '';
};
in rec {
"""

FOOTER = """\
}
"""

def derivation(plugin):
    return TEMPLATE.format(name=plugin.name, version=plugin.version, url=plugin.url, sha=plugin.sha)


def main():
    with open("plugins.nix", "w") as f:
        f.write(HEADER)
        for p in plugins():
            px = versions(p)
            plugin = px.next() # one after latest
            print plugin
            f.write(derivation(plugin))
        f.write(FOOTER)


if __name__ == "__main__":
    main()

#!/home/shmank/flaskServer/.venv/bin/python3
import requests

"""
Script Name: script.py
Description: A clean, modular blueprint for writing Python scripts.
Author: Your Name
Date: 2026-06-19
"""

import sys
import os 
import math
import json


def get_stations(loc_id):
    try:
        response = requests.get('https://radio.garden/api/ara/content/page/' + loc_id)
        if response.status_code == 200:
            data = response.json()
            for channels in data['data']['content']:
                print(channels['title'] + ": ")
                for item in channels['items']:
                    if item['page']['type'] == "channel":
                        print('Title: ' + item['page']['title'])
                        print('Country: ' + item['page']['country']['title'])
                        print('http://radio.garden/api/ara/content/listen/' + item['page']['url'].split("/")[-1] + '/channel.mp3')
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"A network error occurred: {e}")



# helper for find_geo
def is_close(target_geo, given_geo):
	closeness = .50
	return math.dist(target_geo, given_geo) <= closeness

# helper for get_loc_id
def find_geo(json_obj, target_geo):
    if isinstance(json_obj, dict):
        if "geo" in json_obj and is_close(target_geo, json_obj["geo"]):
            return json_obj["id"]
        for value in json_obj.values():
            result = find_geo(value, target_geo)
            if result is not None:
                return result
    elif isinstance(json_obj, list):
        for item in json_obj:
            result = find_geo(item, target_geo)
            if result is not None:
                return result
    return None

# gets the id of the location
def get_loc_id():

	try:
		response = requests.get('http://radio.garden/api/ara/content/places')
    
		if response.status_code == 200:
			data = response.json()
		    # 52.28895497254308, 20.618328365871974	
			loc_id = ((find_geo(data, [  20.618328365871974	, 52.28895497254308])))
			print(loc_id)
			print(get_stations(loc_id))
			
			#print(f"API Version: {data['apiVersion']}")
			#print(f"size: {data['data']['list'][0]['size']}")
		else:
			print(f"Failed to fetch data. Status code: {response.status_code}")

	except requests.exceptions.RequestException as e:
		print(f"A network error occurred: {e}")



def main(args):
	"""Main execution function for the script logic."""
	print("Hello, World!")
  
	

	get_loc_id()

    
	# Your core logic goes here
	return 0

if __name__ == "__main__":
    	# Ensures the script runs only when executed directly, not when imported
    	sys.exit(main(sys.argv[1:]))


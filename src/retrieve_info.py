import pandas as pd
import os
import re
from bs4 import BeautifulSoup
from urllib.request import urlopen
from app import convert_csv_to_gpd

def lstFiles(rootPath, ext):
  '''
  retrieve file path + names based on extension
  '''
  file_list = []
  root = rootPath
  for path, subdirs, files in os.walk(root):
      for names in files: 
          if names.endswith(ext):
              file_list.append(os.path.join(path,names))
  return(file_list)

def createFolder(rootPath, folderName): 
  '''
  Create new folder in root path 
  '''
  folderPath = os.path.join(rootPath, folderName) 
  if not os.path.exists(folderPath):
      os.makedirs(folderPath)
  return folderPath

def get_raw_soup(region, rootUrl):
    url = f'{rootUrl}wraws/{str(region)}.html'
    html= urlopen(url)
    soup = BeautifulSoup(html,"lxml")
    # text = soup.get_text()
    return soup 

def get_date_info(binURL,rootUrl):
    dates = binURL.group(1).replace("rawMAIN", "rawNAME", 1)
    datesURL = rootUrl + dates 
    
    # get start/end dates 
    dateHtml= urlopen(datesURL)
    dateSoup = BeautifulSoup(dateHtml, features="lxml")
    paragraphs = dateSoup.get_text()
    yrs = [int(s) for s in paragraphs.split() if s.isdigit() and len(s) == 4]
    # datetext = dateSoup.get_text()
    return yrs

def get_info_text(binURL,rootUrl):
    info = binURL.group(1).replace("rawMAIN", "wea_info", 1)
    infoURL =  rootUrl + info 
    infoHtml= urlopen(infoURL)
    infoSoup = BeautifulSoup(infoHtml, features="lxml")
    infotext = infoSoup.get_text()
    return infotext

def get_latitude_longitude(binURL,rootUrl):
    infotext = get_info_text(binURL,rootUrl)
    latMark = infotext.find('°') 
    latitude = infotext[latMark - 2 : latMark + 8]

    i = infotext.index('°')
    longMark = infotext.index('°', i + 1)
    longitude = infotext[longMark - 3 : longMark + 8]
    return latitude, longitude

def get_all_stations(rootUrl = "https://wrcc.dri.edu/", RegionList = ["ncalst", "ccalst", "scalst"]):
    stationName = [] 
    stationAbbrv = [] 
    mainURL = [] 
    lat = [] 
    long = [] 
    startYr = [] 
    endYr = [] 

    for region in RegionList: 
        soup = get_raw_soup(region, rootUrl)
        for text in soup.find_all('a', href=True):
            binURL = re.search('href="(.*)" onmouseout=', str(text))
            result = re.search("> (.*)California </a>", str(text))
            if result is not None and binURL.group(1)[-3:] not in stationName:
                try: 
                    yrs = get_date_info(binURL,rootUrl)
                    latitude, longitude = get_latitude_longitude(binURL,rootUrl)
                    
                    # append values to empty list 
                    endYr.append(yrs[0])
                    startYr.append(yrs[-1])
                    lat.append(latitude)
                    long.append(longitude)
                    stationName.append(result.group(1))
                    stationAbbrv.append(binURL.group(1)[-3:])
                    mainURL.append(binURL.group(1))
                except: 
                    continue

    RAWSInfoDF = pd.DataFrame({'Station': stationName, 'Abbrv': stationAbbrv, 
                          'URL': mainURL, 'latitude' : lat, 'longitude' : long,
                          'Start Year' : startYr, 'End Year' : endYr})

    return RAWSInfoDF

def get_RAWS_df(inpath):
    RAWSInfoDF = pd.read_csv(inpath, sep=',')
    RAWSInfoDF = RAWSInfoDF.drop(columns=['Unnamed: 0'])
    RAWSInfoDF['latitude'] = (RAWSInfoDF['latitude'] + '.00"N')
    RAWSInfoDF['longitude'] = (RAWSInfoDF['longitude'] + '.00"W')
    return RAWSInfoDF

def dms2dd(degrees, minutes, seconds, direction):
    dd = float(degrees) + float(minutes)/60 + float(seconds)/(60*60);
    if direction == 'W' or direction == 'N':
        dd *= -1
    return dd;

def dd2dms(deg):
    d = int(deg)
    md = abs(deg - d) * 60
    m = int(md)
    sd = (md - m) * 60
    return [d, m, sd]

def parse_dms(dms):
    parts = re.split('[^\d\w]+', dms)
    lat = dms2dd(parts[0], parts[1], parts[2], parts[3])
    return (lat)

def filter_by_year(df, yr):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('(', '').str.replace(')', '')
    df = df[df.end_year > yr].reset_index(drop=True)
    return df

def process_to_finaldf(inpath = 'data/RAWS_Info.csv', yr =2000, outpath = 'data/Raws_info_cleaned.csv'):
    decimal_Lat = [] 
    decimal_Long = [] 
    df = get_RAWS_df(inpath)
    for index, row in df.iterrows():
        decimal_Lat.append(parse_dms(row[3]))
        decimal_Long.append(-1 * parse_dms(row[4]))

    df["decimal_Lat"] = decimal_Lat
    df["decimal_Long"] = decimal_Long

    df = filter_by_year(df, yr)
    
    df.to_csv(outpath, sep=',')
    
    return df


# get all raws station data as df
df = get_all_stations()

# save df into csv
outpath = '../data/RAWS_Info.csv'
df.to_csv(outpath, sep=',')

# process data converting to coordinates and filtering out stations not active since the year 2000 
final_df = process_to_finaldf(inpath = '../data/RAWS_Info.csv', yr =2000, outpath = '../data/RAWS_info_cleaned.csv')

raws_info = pd.read_csv("../data/RAWS_info_cleaned.csv")
raws_info = raws_info.drop(columns=['Unnamed: 0'])

raws_gdf = convert_csv_to_gpd(df = raws_info, outpath = "../data/weather_stations.geojson")
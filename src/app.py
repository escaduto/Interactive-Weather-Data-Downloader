import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import csv
import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
from shapely.geometry import Polygon
import os
import seaborn as sns
import matplotlib.pylab as plt

def createFolder(rootPath, folderName): 
  '''
  Create new folder in root path 
  '''
  folderPath = os.path.join(rootPath, folderName) 
  if not os.path.exists(folderPath):
      os.makedirs(folderPath)
  return folderPath

def convert_csv_to_gpd(df, outpath):
    geometry = [Point(xy) for xy in zip(raws_info.decimal_long, raws_info.decimal_lat)]
    crs = {'init': 'epsg:4326'}
    geo_df = gpd.GeoDataFrame(raws_info, crs=crs, geometry=geometry)
    geo_df.sort_values(by=['station'])
    geo_df = geo_df.drop(columns=['decimal_long', 'decimal_lat'])
    geo_df.to_file(outpath, driver='GeoJSON')
    return geo_df

class SelectStation: 
    def __init__(self, feature_collection, raws_gdf):
        self.feature_collection = feature_collection 
        self.raws_gdf = raws_gdf 

    def get_bounds(self):
        bounds_lst = []
        for i in range(0, len(self.feature_collection['features'])):
            feature_dict = self.feature_collection['features'][i]['geometry']
            bounds = feature_dict['coordinates'][0]
            bounds_lst.append(bounds)
        return bounds_lst

    def bounds_to_gdf(self):
        bounds = self.get_bounds() 
        wkt_bounds = [ Polygon(pol).wkt for pol in bounds ]
        df = pd.DataFrame({'Coordinates': wkt_bounds})
        df['Coordinates'] = gpd.GeoSeries.from_wkt(df['Coordinates'])
        gdf = gpd.GeoDataFrame(df, geometry='Coordinates')
        return gdf

    def getSelectStation(self):
        bounds_gdf = self.bounds_to_gdf()
        bounds_gdf = bounds_gdf.set_crs(self.raws_gdf.crs)
        res_intersection = gpd.overlay(self.raws_gdf, bounds_gdf, how='intersection', keep_geom_type=True)
        return res_intersection

class RetrieveAndSave:    
    def __init__(self, start_date, end_date, raws_gdf, csv_name, filter_by, aggr_by):
        self.start_date = start_date 
        self.end_date = end_date
        self.raws_gdf = raws_gdf
        self.csv_name = csv_name
        self.filter_by = filter_by
        self.aggr_by = aggr_by

    def scrape_data(self, url, dt, station_name):
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        table_rows = soup.find_all("tr",attrs={"class": "data"})

        data_val = []
        for dta in table_rows[:-4]: 
            td = dta.find_all('td')
            row = [i.text.replace('\n', ' ').strip() for i in td]
            row_witout_empty = list(filter(lambda x: x != '', row))
            
            data_val.append(row_witout_empty)

        
        if len(data_val) != 0: 
            return data_val

    def save_to_csv(self, data):
        out_path = createFolder('../data', 'RAWS_CSV')
        row_head = ['Station Name', 'Date', 'Hour', 'Total_Solar_Rad', 'Wind_Avg_mph', 'Wind_Dir_Deg', 
                        'Wind_Max_mph', 'Air_Temp_Avg', 'Fuel_Temp_Avg', 'Fuel_Moist_Per',
                        'Rel_Hum_Per', 'Dew_Point_Deg', 'Wet_Bulb', 'Total_Precip']
        with open(os.path.join(out_path, self.csv_name), 'w') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row_head)
            for row in data:
                writer.writerow(row)

    def cleanCSV(self):
        file_path = os.path.join('../data', 'RAWS_CSV', self.csv_name)
        df = pd.read_csv(file_path)
        df['Datetime'] = df['Date'].str.cat(df['Hour'],sep=" ")  
        df['Datetime'] =  pd.to_datetime(df['Datetime'], format='%Y-%m-%d %I %p')

        df.iloc[-1, df.columns.get_loc('Datetime')] = df.iloc[-1, df.columns.get_loc('Datetime')] + datetime.timedelta(days=1) 

        df['Station Name'] = df['Station Name'].str.strip()

        df = df[['Station Name', 'Datetime', 'Hour'] + list(self.filter_by)]

        df.to_csv(file_path, index=False)
        return df 

    def retrieveRAWS_saveIntoCSV(self, feature_collection):
        P = SelectStation(feature_collection, self.raws_gdf)
        selected_stations = P.getSelectStation().drop_duplicates()
        hrly_data = []      
        for index, rows in selected_stations.iterrows(): 
            sta_name = rows.station 
            delta = self.end_date - (self.start_date - timedelta(days=1))
            # print(sta_name, delta) # change to loading/progress bar 

            # get range of dates
            date_list = [self.end_date - datetime.timedelta(days=x) for x in range(delta.days)]
            
            for dy in date_list: 
                if rows.end_year >= dy.year:
                    # plug into url 
                    dy_str = str(dy.day)
                    mth_str = str(dy.month).zfill(2)
                    yr_str = str(dy.year)
                    # print(dy_str, mth_str, yr_str)
                    url = f'https://raws.dri.edu/cgi-bin/wea_daysum2.pl?stn=c{rows.abbrv.lower()}&day={dy_str}&mon={mth_str}&yea={yr_str[-2:]}&unit=E'
                    
                    # web scrape 
                    dt = yr_str + mth_str + dy_str
                    data_val = self.scrape_data(url, dt, sta_name)
                    new_data_val =[]
                    if data_val != None: 
                        for lst in data_val:
                            lst.insert(0, sta_name)
                            lst.insert(1, dy)
                            new_data_val.append(lst)
                        hrly_data = hrly_data + new_data_val

        self.save_to_csv(hrly_data)
        self.cleanCSV()
        return hrly_data

class DataPrep: 
    def __init__(self, input_filename, daytime_slider, daytime_toggle, aggr_by, select_var): 
        self.input_filename = input_filename 
        self.daytime_slider = daytime_slider
        self.daytime_toggle = daytime_toggle
        self.aggr_by = aggr_by
        self.select_var = select_var

    def readin_data(self):
        data = pd.read_csv(os.path.join('../data', 'RAWS_CSV', self.input_filename))
        return data 

    def get_daytimes(self):
        data = self.readin_data()
        day_start = self.daytime_slider[0]
        day_end = self.daytime_slider[1]
        
        data["Hour"] = data["Hour"].str.split(" ", 1, expand=True)[0]

        data["day_bool"] = np.where((data["Hour"]  >= day_start) & (data["Hour"]  <= day_end), 'Day', 'Night')

        return data 

    def filter_by_daynight(self): #['Daytime Only', 'Nighttime Only', 'Day & Night']
        df = self.get_daytimes()
        if self.daytime_toggle == 'Daytime Only':
            df = df[df['day_bool'] == 'Day']
        
        elif self.daytime_toggle == 'Nighttime Only':
            df = df[df['day_bool'] == 'Night']
        else: 
            pass
        return df 

    def aggr_data(self):
        '''
        [TODO] keep column names Datetime, Station Name, day_bool !!!
        '''
        df = self.filter_by_daynight()
        if self.aggr_by == 'Daily':
            df = df.groupby([pd.Grouper(key='Datetime', freq='D'), 
                            pd.Grouper('Station Name'),
                            pd.Grouper('day_bool')]).mean()

        elif self.aggr_by == 'Monthly':
            df = df.groupby([pd.Grouper(key='Datetime', freq='M'), 
                             pd.Grouper('Station Name'),
                             pd.Grouper('day_bool')]).mean()
        
        elif self.aggr_by == 'Annually':
            df = df.groupby([pd.Grouper(key='Datetime', freq='A-DEC'), 
                            pd.Grouper('Station Name'),
                            pd.Grouper('day_bool')]).mean()
        else: 
            pass

        df.to_csv(os.path.join('../data', 'RAWS_CSV', 'new_sample.csv'), index=False)
        return df 

    def filter_byVar(self):
        df = self.aggr_data()
        df = df[['Station Name', 'day_bool', 'Datetime', self.select_var]]
        return df 


class PlotData: 
    def __init__(self, df, select_station, select_var): 
        self.df = df 
        self.select_station = select_station 
        self.select_var = select_var 

    def create_plot(self):
        filter_df = self.df[self.df['Station Name'] == self.select_station]
        sns.set_style('whitegrid', {'legend.frameon':True, 'framealpha':1})
        plt.figure(figsize=(10,5))
        filter_df = self.df[self.df['Station Name'] == self.select_station]
        chart = sns.lineplot(data= filter_df, x="Datetime", y=self.select_var)

        chart.set(xticks=filter_df.Datetime[2::8])
        plt.xticks(
            rotation=80, 
            horizontalalignment='right',
            fontweight='light',
            fontsize='x-small' )


        None
        plt.show()
        
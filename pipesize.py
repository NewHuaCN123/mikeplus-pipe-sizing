#!/usr/bin/env python
# coding: utf-8

# Script reuses input by Gediminas Kiršanskas gedaskir


#### Global parameters ####

# Per default the diameters have a step size of 50 mm, meaning that the script will use 50 mm, 100 mm, 150 mm, ...
# Change 'step' if you prefer e.g. 100 mm. Parameter used in section 'Find next commercially available diameter'.
step = 50


#### Import necessary libraries ####

print('Importing necessary libraries...')


# MIKE IO 1D, needs Pandas and Numpy
import mikeio1d
from mikeio1d.res1d import Res1D, QueryDataNode, QueryDataReach,ResultData, mike1d_quantities, ResultData
import pandas as pd
import numpy as np

# connection to MIKE+ database:
import sqlite3

# file and folder manipulation for input and output:
import os

# find files faster
from fnmatch import fnmatch

# only used when checking speed:
# import time


# if in doubt about MIKE IO, print location of mikeio:
# print(mikeio1d.__file__)


#### Define functions ####

print('Defining functions...')


# compute slope from first and last GridPoint, returns absolute value in percent, currently not used:
def get_slope(reach):
    grid_points = list(reach.GridPoints)
    gp_first = grid_points[0]
    gp_last = grid_points[-1]
    length = reach.Length
    slope = ((gp_first.Z - gp_last.Z) / length)*100
    return abs(slope)


# returns the time series (?) for a specific Quantity ID
def get_data_item(reach, quantity_id):
    item = None

    for data_item in list(reach.DataItems):
        if data_item.Quantity.Id == quantity_id:
            item = data_item
            break

    return item


# Get min and max value and times for a any model element (not only reaches)
#       reach...DHI.Mike1D.ResultDataAccess.Res1DManhole object or similar
#       timeslist...list of DateTime objects
#       quantity_id...string with quantity (default ist "Discharge")

def get_minmax_value_result_file(reach, times_list, quantity_id="Discharge"):
    item = get_data_item(reach, quantity_id)

    min_value, min_time = None, None
    max_value, max_time = None, None   
    
    try:
        time_data = item.TimeData
        for time_step_index in range(time_data.NumberOfTimeSteps):
            
            for element_index in range(time_data.NumberOfElements):
                value = time_data.GetValue(time_step_index, element_index)
                if min_value is None or value < min_value:
                    min_value = value 
                    min_time = times_list[time_step_index].ToString()

                if max_value is None or value > max_value:
                    max_value = value 
                    max_time =  times_list[time_step_index].ToString()
    
    except:
        time_data = None
    
    return min_value, min_time, max_value, max_time


#### Find res1d and sqlite files ####

print('Searching res1d and sqlite files...')


def isres1dfile(filename):
    return fnmatch(filename, '*.res1d')


cwd = os.getcwd()
print('Current directory: ' + cwd)


os.listdir(cwd)


myRes1dFiles = sorted(filter(isres1dfile, os.listdir(cwd)), key=os.path.getmtime, reverse=True)
print('Number of res1d-files in directory: ' + str(len(myRes1dFiles)))


# pick the first res1d-file
oneRes1dFile = myRes1dFiles[0]

print('Latest res1d-file will be used: ' + oneRes1dFile)


# create a list of sqlite-files
mySQLiteFiles = [file for file in os.listdir(cwd) if fnmatch(file, '*.sqlite')] 

if len(mySQLiteFiles) > 1:
    print('ATTENTION, there is more than one sqlite-Database!')

# pick the first sqlite-file
oneSQLiteFile = mySQLiteFiles[0]

print('Current MIKE+ database: ' + oneSQLiteFile)


#### Create list of links from res1d ####

print('Creating list of links from res1d...')


# create a Res1d-object
res1d = Res1D(oneRes1dFile)

reaches = list(res1d.data.Reaches)

times_list  = list(res1d.data.TimesList)

simulation_start = res1d.data.StartTime


#### Prepare desired Link results ####

print('Preparing desired link results...')


#initialize lists
Link_ID=[]
Qmax=[]
Qmax_time=[]


# call necessary informations from initially defined functions
for reach in reaches:

    # get data
    name = reach.Name
    q_minmax_data = get_minmax_value_result_file(reach, times_list, "Discharge")
       
    # append to lists
    Link_ID.append(name)
    Qmax.append(q_minmax_data[2])
    Qmax_time.append(q_minmax_data[3])
    


# create dictionary with link lists
dict_res1d_links = {'Link_ID':Link_ID,'Qmax':Qmax, 'Qmax_time':Qmax_time}


# create dataframe from dictionary
df_res1dLink=pd.DataFrame(dict_res1d_links)

# set index on Link_ID:
df_res1dLink =  df_res1dLink.set_index('Link_ID')

#### Connect to database and retreive msm_Link data ####

print('Connecting to database and retreiving msm_Link data...')


# establish connection to MIKE+ database:
con = sqlite3.connect(oneSQLiteFile)


# pick columns from 'msm_Link':
df_msmLink = pd.read_sql_query("SELECT MUID, diameter, slope, Manning, usrOrigDiam from msm_Link", con)


# set index on 'muid'
df_msmLink = df_msmLink.set_index('muid')


#### Drop records of no interest ####

# only used when checking speed:
# tic = time.perf_counter()


##### Check column usrOrigData #####

df_msmLink['usrorigdiam'].count()


# the following should look nicer using using pandas.series.count
if len(df_msmLink.loc[df_msmLink['usrorigdiam'] > 0]) == 0:
    print('Column usrOrigDiam is empty. All records in msm_Link will be used: ' + str(len(df_msmLink)))
else:
    print('All records in msm_Link: ' + str(len(df_msmLink)))
    df_msmLink = df_msmLink.loc[df_msmLink['usrorigdiam'] > 0]
    print('Records in msm_Link with given usrOrigDiam: ' + str(len(df_msmLink)))


##### Make sure all records have a value in column Manning #####

countEmptyManning = len(df_msmLink.loc[df_msmLink['manning'].isna()])

if countEmptyManning > 0:
    print('ATTENTION: All records of interest must have a value in column Manning.')
    print('Dropping records withoung Manning: ' + str(countEmptyManning))
    df_msmLink = df_msmLink.loc[df_msmLink['manning'] > 0]
    
print('Remaining records in msm_Link with value in column Manning: ' + str(len(df_msmLink)))    


##### Records with negative slope or without local Manning #####

df_msmLink.loc[df_msmLink['slope']<0]


countNegSlope = len(df_msmLink.loc[df_msmLink['slope']<=0])

if countNegSlope > 0:
    df_msmLink = df_msmLink.loc[df_msmLink['slope'] > 0]
    print('ATTENTION: Method doesn\' work with negative slope.')
    print('Dropping records with a negative slope: ' + str(countNegSlope))
    
print('Remaining records with a positive slope : ' + str(len(df_msmLink)))

# only used when checking speed:
# tac = time.perf_counter()
# print(tac-tic)


#### Join msm_Link with Link results ####

print('Joining msm_Link with Link results...')


dfm = pd.merge(df_res1dLink, df_msmLink, left_index=True, right_index=True)

#### Compute new diameter ####

print('Computing new diameter...')


##### Apply formula #####

def designDiam(Q, I, M):
    D = Q ** 0.375 * (0.312 * (I/100) ** 0.5 * M) ** -0.375
    return D
    


# dfm['newdiameter'] = dfm['Qmax'] ** 0.375 * (0.312 * (dfm['slope']/100) ** 0.5 * dfm['manning']) ** -0.375


dfm['newdiameter'] = designDiam(dfm['Qmax'], dfm['slope'], dfm['manning'])


##### Only keep records where new diameter larger than original diamater #####

dfm = dfm.loc[dfm['newdiameter'] > dfm['usrorigdiam']]
print('Records with diameter larger than original: ' + str(len(dfm[dfm.newdiameter > dfm.usrorigdiam])))


# only used when checking speed:
# toc = time.perf_counter()
# print(toc-tic)


##### Find next commercially available diameter #####

# Parameter 'step' is defined at the beginning of the script.
dfm['newdiameter'] = np.ceil(dfm.newdiameter * 1000 / step) / (1000 / step)
##### Only keep records where new diameter is different from last iteration #####

dfm = dfm.loc[dfm['newdiameter'] != dfm['diameter']]
print('Records with diameter different from last iteration: ' + str(len(dfm)))


#### Write diameter back to MIKE+ database ####

##### Reduce dataframe and convert back to list of tuples #####

print('Reducing dataframe and converting back to list of tuples...')


# create dataframe with index and newdiameter only
# https://pandas.pydata.org/docs/getting_started/intro_tutorials/03_subset_data.html
dfr = dfm[["newdiameter"]]


# https://datatofish.com/index-to-column-pandas-dataframe/
#dfm.reset_index(inplace=True)
#dfm = dfm.rename(columns = {'index':'muid'})


# https://stackoverflow.com/questions/9758450/pandas-convert-dataframe-to-array-of-tuples
data = list(dfr.itertuples(name=None))
# sql command needs diameter as first parameter and muid as second parameter
datarev =  [tuple(reversed(t)) for t in data]
##### Update sqlite database #####

print('Updating database...')


cursor = con.cursor()


statement = 'Update msm_Link set Diameter = ? WHERE muid = ? '


cursor.executemany(statement,datarev)


con.commit()


cursor.close()


n = len(datarev)
print(str(n) + ' records updated')


# Wait for input. If the script was started with double click, the command window will close.
# If the script was started within the command window, the window remains open.
# input('Press ENTER to finish')



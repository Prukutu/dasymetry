""" This script calls dasymetry.py. User can modify or call only the
    methods they want to use. Please see the namelist file for info
    on the parameters.
"""

import sys
from pathlib import Path

# enter your dasymetry path
dasypath = '/home/luis/github/dasymetry/'
workdir = Path('/home/luis/Documents/Research/projects/test_dasymetry/')

sys.path.append(dasypath)

import dasymetry as dasy
import matplotlib.pyplot as plt

dasy = dasy.Dasymetry(workdir)
dasy.load_namelist(dasy.rundir)
dasy.load_source_files(dasy.configdict)

# Pre-process blocks and lots for disaggregation
dasy.getOverpopParcels(dasy.parcel_df, dasy.block_df)

dasy.assignParcels(dasy.parcel_df, dasy.block_df)

# print('Total CB population:')
# print(dasy.block_df['pop10'].sum())

# disaggregate
dasy.blocksToOverpop(dasy.parcel_df, dasy.block_df)
dasy.disaggregate(dasy.parcel_df, dasy.block_df)
dasy.disaggregate_leftover(dasy.parcel_df, dasy.block_df)


# Write output
dasy.writeOutput('test.csv', dasy.parcel_df)

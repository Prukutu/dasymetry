import sys
sys.path.append('/home/luis/github/dasymetry/')

import dasymetry as dasy
import matplotlib.pyplot as plt

dasy = dasy.Dasymetry('/home/luis/Documents/Research/projects/test_dasymetry/')
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

# print('After disaggregating into res units:')
# print(dasy.block_df['pop10'].sum())

# Plot results
# fig, ax = plt.subplots(figsize=(16, 9))
# im = dasy.parcel_df.plot(column='pop10',
#                          cmap='YlOrRd',
#                          scheme='fisher_jenks',
#                          edgecolor='black',
#                          legend=True,
#                          ax=ax,
#                          k=10,
#                          linewidth=.25)
# leg = ax.get_legend()
# leg.set_bbox_to_anchor((.35, .2, 0.2, 0.2))
# 
# fig.savefig('test.png', bbox_inches='tight')

# Write output
dasy.writeOutput('ACS2017_totpop_mappluto2017.csv', dasy.parcel_df)

import geopandas as gpd
from tqdm import tqdm


class Dasymetry:

    """ Class collecting tools to disaggregate socio-demographic data into
        discrete parx   cels.
    """

    def __init__(self, rundir):

        # Add any top-level parameters here.
        self.rundir = rundir

        return None

    def load_namelist(self, rundir):
        """ Load the configuration file that contains location of input files,
            as well as user selected parameters (e.g., max household size).

            Input:
            ------
            rundir: running directory containing the file 'namelist.config'

            Output:
            -------
            Creates dictionary with name, parameter pairs as a class attribute
        """

        def clean_lot_list(lot_list):
            """ Function to remove empty items from namelist.config fields.
                We do this because it's easier to remove empty items than
                it is to turn 1-item fields into a list.

                Input:
                ------
                lot_list: list read from namelist.config
            """
            newlist = [item for item in lot_list if item != '']
            return newlist

        def acre_to_sqft(area_val, conversion=43560):
            """ Converts from area_val (in people/acre) to people/sqft

                Input:
                ------
                area_val: Array-like values representing parcel data in people
                per square feet (EPSG 2263 native units)
            """

            return area_val/conversion

        def assign_lot_codes():
            """ Assign the list of landuse codes belonging to each lot type
                in the namelist.config field lot_types

                lot_types are in order of population assignment priority,
                (e.g., lot_code_1 corresponds to the first item in lot_types)
            """

            for n, lot in enumerate(self.configdict['lot_types']):
                code_name = lot + '_codes'
                codes = 'lot_codes_' + str(n + 1)

                lot_list = clean_lot_list(self.configdict[codes])
                self.configdict[code_name] = lot_list

                # Remove original lot_code entry from configdict
                del self.configdict['lot_codes_' + str(n + 1)]

            return None

        with open(rundir + 'namelist.config') as f:
            lines = f.readlines()

            # Now that the namelist is a list, we don't need whitespace or
            # empty lines
            lines = [l.strip() for l in lines]
            lines = list(filter(None, lines))

            linesplit = [l.replace(' ', '').split('=') for l in lines]
            params = {l[0]: l[1:][0] for
                      l in linesplit}

            params = {key: params[key].split(',') for key in params.keys()}

            # Some parameters should be floats rather than strings.
            numerical_params = ('top_hh_size', 'top_den_allowed')
            for key in numerical_params:
                params[key] = [float(val) for val in params[key]]

            params = {key: params[key][0] if len(params[key]) == 1 else
                      params[key] for key in params.keys()}

        # Allowed densities are in units of people/acre. Convertt to projection
        # units (1 acre = 43560 sq. ft)
        params['top_den_allowed'] = [acre_to_sqft(val) for val
                                     in params['top_den_allowed']]
        self.configdict = params
        self.res_units = params['res_units']

        # Call function to assign landuse codes to their corresponding names
        assign_lot_codes()

    def load_geodataframe(self, filename, fid='bbl'):
        """ Method to load geometric data. Uses geopandas to load a shapefile
            into a GeoDataFrame, then performs some light cleaning of column
            names.

            Input:
            ------
            filename (str): string describing file name of dataset

            fid (str): Column name of parcel identifier.
            Default bbl from NYC MapPLUTO.

            Output:
            -------
            gdf: GeoDataFrame object containing data and geometry.
        """

        # Make the feature id a class attribute
        # self.parcel_fid = fid

        print('Loading data...')

        df = gpd.read_file(filename)

        print(filename + ' loaded!')

        # Make all column names lowercase
        df.columns = map(str.lower, df.columns)

        # Make fid into the GeoDataFrame index.
        # df[fid] = df[fid].astype(int)
        df.set_index(fid, inplace=True)

        return df

    def load_source_files(self, configdict):
        """ Loads the source population and parcel datasets. Calls
            load_geodataframe using parameters in the configuration dict.

            Input:
            ------
            configdict: configuration dictionary from load_namelist

            Output:
            -------
            Creates a GeoDataFrame object for each input file as a class
            attribute.
        """

        population = (configdict['run_dir']
                      + configdict['input_dir']
                      + configdict['population_file'])

        block_df = self.load_geodataframe(population,
                                          configdict['population_fid'])
        block_df = block_df.loc[:, self.configdict['block_fields']]

        parcels = (configdict['run_dir']
                   + configdict['input_dir']
                   + configdict['parcels_file'])

        parcel_df = self.load_geodataframe(parcels,
                                           configdict['parcels_fid'])

        parcel_df = parcel_df.loc[:, self.configdict['parcel_fields']]
        # Create a new column in parcel_df, pop_name, to hold populations.
        # Initialize with zero.
        parcel_df[configdict['pop_name']] = 0
        parcel_df.loc[:, 'numfloors'][parcel_df.loc[:, 'numfloors'] < 1] = 1

        # Make sure the blocks and parcels are in the same map projection
        if block_df.crs != parcel_df.crs:
            block_df = block_df.to_crs(parcel_df.crs)

        self.parcel_df = parcel_df
        self.block_df = block_df

        pop_name = self.configdict['pop_name']
        remaining = str(self.parcel_df[pop_name].sum())
        print('Total population disaggregated: ' + remaining)

    def writeOutput(self, filename, parcels, subset=None):
        pop_name = self.configdict['pop_name']
        print('Writing output to CSV...')
        parcels[pop_name].to_csv(filename, header=True)
        print('Done!')

    def getOverpopParcels(self, parcel_df, block_df):
        """ Performs a spatial left join between parcels and blocks dataset.
            Then keep only the parcels that contain > 1 population blocks.
        """
        # Create a copy of block_df with block centroids as geometry
        parcel_df['overpopulated'] = False
        block_centroid = block_df.copy()
        block_centroid['geometry'] = block_centroid.centroid

        # Find the lots that have > 1 census block within
        overpop_parcels = gpd.sjoin(parcel_df, block_centroid)
        # Parcels that have more than one entry are considered overpopulated,
        # since they have > 1 census block within them.
        overpop_bool = overpop_parcels.index.duplicated(keep=False)
        overpop_index = overpop_parcels.loc[overpop_bool].index
        overpop_index = list(set(overpop_index))
        parcel_df['overpopulated'].loc[overpop_index] = True

        print('Blocks assigned to overpopulated parcels')

        return None

    def assignParcels(self, parcel_df, block_df):
        """ Assigns parcels to the block that contains them, excluding where
            parcel_df['overpolated'] is True.
        """

        # Create a new column in block_df to store contained parcels
        block_df['parcels'] = [[]] * len(block_df)
        block_df['parcels'] = block_df['parcels'].astype(object)

        # Get subset of non-overpopulated parcels, then sjoin to block_df
        parcels_no_overpop = parcel_df[parcel_df['overpopulated'] == False]
        parcels_centroid = parcels_no_overpop.copy()

        # To perform the sjoin we need a column named 'geometry'
        parcels_centroid['geometry'] = parcels_centroid.centroid
        blocks_joined = gpd.sjoin(block_df, parcels_centroid)

        blocks_unique_index = list(set(blocks_joined.index))

        # For each block, list all parcels. Then convert to a GeoSeries to
        # append to block_df
        parcel_dict = {key: [blocks_joined.loc[key, 'index_right']] if
                       not hasattr(blocks_joined.loc[key, 'index_right'],
                                   '__iter__') else
                       list(blocks_joined.loc[key, 'index_right'].values)
                       for key in blocks_unique_index}

        block_df['parcels'] = gpd.GeoSeries(parcel_dict)

        # Remove census blocks that intersect no parcels
        # block_df.dropna(subset=['parcels'], inplace=True)

        return None

    def blockToParcel(self, block, parcel, numpeople):
        """ Method to transfer a number of people from a census block
            to a parcel contained within it. The block's population value
            is decreased by numpeople, while the parcel's population value
            is increased by numpeople.

            Input:
            ------
            block: index of source census block (np.int64)
            parcel: index of source parcel (np.int64)
            numpeople: Number of people to be transfered (np.int64)

            Output:
            -------
            None
        """

        # First, check that the parcel is actually contained in the block
        # missingmsg = 'Selected parcel not found in this block'
        # assert parcel in self.block_df.loc[block, 'parcels'], missingmsg

        parcels = self.parcel_df
        blocks = self.block_df

        pop_name = self.configdict['pop_name']

        parcels.loc[parcel, pop_name] = (parcels.loc[parcel, pop_name]
                                         + numpeople)
        blocks.loc[block, pop_name] = blocks.loc[block, pop_name] - numpeople

        return None

    def blocksToOverpop(self, parcels, blocks):
        """ Add the population of blocks within overpopulated parcels (ie,
            parcels that contain > 1 census block) and add to parcel.
        """
        check = 'overpopulated' in parcels.columns
        msg = 'Run getOverpopParcels method!'
        assert check, msg

        pop_name = self.configdict['pop_name']
        # Get a copy withof blocks with centroids as geometry
        block_centroid = blocks.copy()
        block_centroid['geometry'] = block_centroid.centroid

        # We only want to operate on overpopulated parcels.
        overpop_parcels = parcels[parcels['overpopulated'].__eq__(True)]

        # Spatial join of the overpopulated parcels with the source blocks.
        overpop_join = gpd.sjoin(overpop_parcels, block_centroid)

        # Add the populations of all blocks, by containing parcel, then
        # assign added value to parcels_df.
        popname_right = pop_name + '_right'
        pop = overpop_join.groupby(by=overpop_join.index).sum()[popname_right]

        parcels.loc[pop.index, pop_name] = pop

        # Now we "empty" out the census blocks in the overpop parcels
        blocks.loc[overpop_join['index_right'], pop_name] = 0

        remaining = str(self.parcel_df[pop_name].sum())
        print('Total population disaggregated: ' + remaining)

        return None

    def disaggregate(self, parcels, blocks):
        """ Method containing main disaggregation logic. Based on Khila et al
            (2019).

        """

        # Define functions used in the disaggregation logic
        def sum_units(parcel_list):
            """ Function to sum the number of residential units of all parcels
                contained in a single census block.

                Input:
                ------
                blockid: Census block ID, used as index in self.blocks_df
            """
            contained = parcels.loc[parcel_list,
                                    self.configdict['res_units']]
            contained_sum = contained.sum()
            return contained_sum

        def compute_pop_resunit(blocks):
            """ Compute the number of people per contained residential units
            """
            pop_name = self.configdict['pop_name']
            contained = 'contained_resunits'

            blocks['pop_resunits_ratio'] = blocks[pop_name]/blocks[contained]

        def distribute_by_resunits(blocks, how='compute'):
            """ Distribute population from a census block to its contained
                parcels according to its proportion of residential units.
            """
            unitresname = self.configdict['res_units']
            pop_name = self.configdict['pop_name']
            top_hhsize = self.configdict['top_hh_size']

            # Looping through all blocks for now. We can think of other ways
            # to do this (maybe an "apply"?) to speed it up.
            for blockid, row in tqdm(blocks.iterrows()):
                total_resunits = blocks.loc[blockid, 'contained_resunits']
                # Call blockToParcel
                for parcel in blocks.loc[blockid, 'parcels']:
                    # Compute proportion of res units per parcel
                    if how == 'compute':
                        proportion = parcels.loc[parcel,
                                                 unitresname]/total_resunits
                        numpeople = blocks.loc[blockid, pop_name]*proportion
                    elif how == 'max':
                        numpeople = top_hhsize*parcels.loc[parcel, unitresname]
                    else:
                        raise Exception('kwarg how ' + how + ' is invalid')

                    # Call blockToParcel to assign numpeople to parcel
                    self.blockToParcel(blockid, parcel, numpeople)

        top_hh_size = self.configdict['top_hh_size']
        pop_name = self.configdict['pop_name']
        # Subset blocks to only those that contain parcels. We do this in Case
        # our census block data does not perfectly align with parcels data.
        blocks_withparcels = blocks.dropna(subset=['parcels'])

        # create a new column to hold the total residential units in a block
        # blocks_withparcels.loc[:, 'contained_resunits'] = 0

        block_res = blocks_withparcels.loc[:, 'parcels'].apply(sum_units)
        blocks.loc[block_res.index, 'contained_resunits'] = block_res.values

        # Compute the block population per residential units ratio
        compute_pop_resunit(blocks)

        # Get all blocks where pop_resunits_ratio < top_hh_size
        # blocks_below_tophh
        below_tophh = blocks[blocks['pop_resunits_ratio'] <= top_hh_size]
        above_tophh = blocks[blocks['pop_resunits_ratio'] > top_hh_size]

        # Distribute population based on proportion of residential units.
        distribute_by_resunits(below_tophh, how='compute')

        # For lots where hh_size is above allowed value
        distribute_by_resunits(above_tophh, how='max')

        blocks.loc[:, pop_name][blocks[pop_name] < 0.25] = 0
        blocks.dropna(subset=['parcels'], inplace=True)

        remaining = str(self.parcel_df[pop_name].sum())
        print('Total population disaggregated: ' + remaining)

        return None

    def disaggregate_leftover(self, parcels, blocks):
        """ This method collects all populations in blocks that was not
            assigned to parcels with residential units, and assigns them
            to parcels of various lot types, in the order found in the
            namelist variable called lot_types. Population is assigned, by
            area proportion, up to a density of top_den_allowed.
        """

        pop_name = self.configdict['pop_name']

        def allowable():

            area = parcels.loc[:, 'lotarea']
            numfloors = parcels.loc[:, 'numfloors']
            current_pop = parcels.loc[:, pop_name]

            allowed = max_dens*area*numfloors - current_pop
            allowed[allowed < 0] = 0

            return allowed

        def distribute_by_areaproportion(blockid, remainder=False):
            subset = parcels.loc[blocks_left.loc[blockid, 'parcels']]
            subset = subset[subset['landuse'].isin(code)]

            if remainder is False:
                subset = subset[subset['allowed'] > 0]

            total_area = subset['lotarea'].sum()
            subset['areaprop'] = subset['lotarea']/total_area

            if len(subset) == 1:
                if remainder is False:

                    numpeople = subset['allowed'].values[0]
                else:
                    # print('Distributing reminder population')
                    numpeople = blocks.loc[blockid, pop_name]

                self.blockToParcel(blockid,
                                   subset.index[0],
                                   numpeople)

            elif len(subset) == 0:
                pass

            else:
                for bbl in subset.index:
                    numpeople = subset.loc[bbl,
                                           'areaprop']*blocks.loc[blockid,
                                                                  pop_name]
                    if remainder is False:
                        if (numpeople < subset.loc[bbl, 'allowed']):
                            self.blockToParcel(blockid, bbl, numpeople)
                        else:
                            numpeople = subset.loc[bbl, 'allowed']
                            self.blockToParcel(blockid, bbl, numpeople)
                    else:
                        self.blockToParcel(blockid, bbl, numpeople)

            return None

        for n, lot_type in enumerate(self.configdict['lot_types']):
            max_dens = self.configdict['top_den_allowed'][n]
            codename = '_'.join([lot_type, 'codes'])
            code = self.configdict[codename]
            parcels['allowed'] = allowable()

            blocks_left = blocks[blocks[pop_name] > 0]
            print('Distributing by area proportion')
            for blockid, row in tqdm(blocks_left.iterrows()):
                distribute_by_areaproportion(blockid)

        # We take whatever folks are left from the previous step, and we
        # assign them to the landuse types in lot_types, without regard to
        # the allowable field.
        for n, lot_type in enumerate(self.configdict['lot_types']):
            codename = '_'.join([lot_type, 'codes'])
            code = self.configdict[codename]

            blocks_left = blocks[blocks[pop_name] > 0]
            print('Distributing the leftovers...')
            for blockid, row in tqdm(blocks_left.iterrows()):
                distribute_by_areaproportion(blockid, remainder=True)

        remaining = str(self.parcel_df[pop_name].sum())
        print('Total population disaggregated: ' + remaining)

        return None

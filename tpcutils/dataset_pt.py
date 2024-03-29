import sys,os

import numpy as np
import pandas as pd

import torch
from torch.utils.data import Dataset,IterableDataset
import torch.nn.functional as F
import operator
import copy

import ROOT

from tpcutils.data import DataHandler,SeparatedDataHandler
from tpcutils.data import select_tpc_clusters_idx

# ROOT.gInterpreter.ProcessLine('#include "../tpcio/TrackTPC.h"')
ROOT.gInterpreter.ProcessLine('#include "/Users/joachimcarlokristianhansen/st_O2_ML_SC_DS/TPC-analyzer/TPCTracks/py_dir/tpcio/TrackTPC.h"')
# ROOT.gInterpreter.ProcessLine('#include "/home/kaare/alice/tpc-track-moving/tpcio/TrackTPC.h"')
#### PYTORCH

#Legacy
class TPCClusterDataset(Dataset):
    def __init__(self, tracks_path, mov_path, transform=False,np_data=True):

        self.X = DataHandler(tracks_path,np_data)
        self.y = SeparatedDataHandler(mov_path,np_data)['xamP'][:,2:]


        self.transform = transform

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        x = self.X[idx,:]
        y = self.y[idx,:]

        if self.transform:
            x = self._transform(x)
            y = self._transform(y)

        # x_tensor = torch.tensor(x,dtype=torch.float64)
        # y_tensor = torch.tensor(y,dtype=torch.float64)
        x_tensor = torch.from_numpy(x).float()
        y_tensor = torch.from_numpy(y).float()


        return x_tensor,y_tensor

    def _transform(self,array):
        return (array - array.min())/(array.max()-array.min())

    def _shape(self,):
        return self.X[2,:].shape[0]

#Legacy
class TPCClusterDatasetConvolutional(Dataset):
    def __init__(self, tracks_path, mov_path,TPC_settings, transform=False,tpcNorm=False,np_data=True):



        self.X = SeparatedDataHandler(tracks_path,TPC_settings,np_data)
        self.Y = SeparatedDataHandler(mov_path,TPC_settings,np_data)
        self.y = self.Y['xamP']

        if tpcNorm:
            self.X['xyz'] = (self.X['xyz'] + 260)/(260+260)


        self._TPCDistortions = self.X['xyz'] - self.Y['xyz']
        self._PADDists = self.X['pads']

        self.x = np.column_stack((self._TPCDistortions,self._PADDists[:,np.newaxis,:]))

        self.transform = transform

        self.index_update = 6

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):

        x = self.x[idx,...]
        xamP = self.X['xamP'][idx,...]



        y = self.y[idx,2:]




        if self.transform:
            x = self._transform(x)
            y = self._transform(y)



        # x_tensor = torch.tensor(x,dtype=torch.float64)
        # y_tensor = torch.tensor(y,dtype=torch.float64)
        x_tensor = torch.from_numpy(x).float().unsqueeze(0)
        y_tensor = torch.from_numpy(y).float()

        mP_tensor = torch.from_numpy(xamP).float()


        tensor_data = {}
        tensor_data['input_xyz_row'] = x_tensor
        tensor_data['mP'] = mP_tensor
        tensor_data['target'] = y_tensor

        return tensor_data

    def _transform(self,array):
        return (array - array.min())/(array.max()-array.min())


class TPCTreeCluster(Dataset):
    def __init__(self, file,transform=False,conf=None):

        self._file = file

        self.tpcIni = self._file.Get("tpcIni")
        self.tpcMov = self._file.Get("tpcMov")
        # tree_key tpcIni has key: iniTrackRef
        # tree_key tpcMov has key: movTrackRef

        self.EntriesIni = self.tpcIni.GetEntries()
        self.EntriesMov = self.tpcMov.GetEntries() 

        if conf.DATA_PARAMS.LIMIT_SET:
            self.EntriesMov = conf.DATA_PARAMS.NSAMPLES



        self.tpcMaxRow = 159 # 159 rows/max number of tpc clusters for padding
        self.ndimTPC = 250
        self.nKalmanFits = 6

        self.transform=transform


        if conf is not None:
            self.config= conf

        clusters = self.config.DATA_PARAMS.TPC_SETTINGS.TPC_CLUSTERS
        #removed X,Alpha..
        self.__shape = 5 + (clusters*3) + clusters + 1 # 7 ini params, clx,cly,clz, ini_clz, dz -- no more ,sector,row

        self.NormArr = np.array([250,250, 1, 5, 40])


    def _padForClusters(self,array):
        return np.pad(array,(0,self.tpcMaxRow-len(array)),"constant")

    def _shape(self):
        return self.__shape


    def __iniConstruct(self,):

        #construct ini vector
        ini_clSector = np.array(self.tpcIni.clSector)
        ini_clRow = np.array(self.tpcIni.clRow)

        iniX = self.tpcIni.iniTrackRef.getX()

        iniAlpha = self.tpcIni.iniTrackRef.getAlpha()

        iniY = self.tpcIni.iniTrackRef.getY()
        iniZ = self.tpcIni.iniTrackRef.getZ()
        iniSnp = self.tpcIni.iniTrackRef.getSnp()
        iniTgl = self.tpcIni.iniTrackRef.getTgl()
        iniQ2Pt = self.tpcIni.iniTrackRef.getQ2Pt()

        #ini toc clusters
        ini_clX = self.tpcIni.clX
        ini_clY = self.tpcIni.clY
        ini_clZ = self.tpcIni.clZ

        #ini_counter = self.tpcIni.counter
        
        ini_vec = np.array([iniY, iniZ, iniSnp, iniTgl, iniQ2Pt])
        ini_vec = self.normalize_vector(ini_vec)
        # X Alpha Y Z Snp Lambda q2 x y z sector row
        return iniX, iniAlpha, ini_vec, ini_clX, ini_clY, ini_clZ, ini_clSector, ini_clRow

    def __movConstruct(self):

        #construct mov vector or rather target
        MovY = self.tpcMov.movTrackRef.getY()
        MovZ = self.tpcMov.movTrackRef.getZ()
        MovSnp = self.tpcMov.movTrackRef.getSnp()
        MovTgl = self.tpcMov.movTrackRef.getTgl()
        MovQ2Pt = self.tpcMov.movTrackRef.getQ2Pt()

        
        #np_target = np.array([ MovY, MovZ]) 
        mov_vec = np.array([MovY, MovZ, MovSnp, MovTgl, MovQ2Pt])
        mov_vec = self.normalize_vector(mov_vec)
        #construct moved tpc clusters
        mov_clX = self.tpcMov.clX
        mov_clY = self.tpcMov.clY
        mov_clZ = self.tpcMov.clZ
        dz = np.array([self.tpcMov.dz]) / self.ndimTPC
        # imposedTB = np.array([self.tpcMov.imposedTB])

        # n_copy = self.tpcMov.copy
        # maxCopy = self.tpcMov.maxCopy

        # mov_counter = self.tpcMov.counter
        # Y Z Snp Lambda q2pt
        return mov_vec, mov_clX, mov_clY, mov_clZ, dz, #imposedTB#, mov_counter, n_copy, maxCopy

    def __match_tracks(self):

        counter = self.tpcMov.counter
        # n_copy = self.tpcMov.copy
        # maxCopy = self.tpcMov.maxCopy

        
        self.tpcIni.GetEntry(counter)


    def _getDistortionEffects(self,arr1,arr2):
        diff = list(map(operator.sub, arr1, arr2))
        return diff

    def _checkVectorlen_(self,array):

        if len(array) != self.__shape:
            # return np.pad(array,(0,self.__shape-len(array)),"constant")
            # return F.pad(array, (0,self.__shape-len(array)), "constant", 0)
            return F.pad(array, (array + self.__shape+10-len(array)), "constant", 0)
        else:
            return array

    def _create_target(self,ini,mov,dz):
        
        Y_dis = mov[0] - ini[0]
        Z_dis = mov[1] + dz - ini[1]
        Snp_dis = mov[2] - ini[2]
        Tgl_dis = mov[3] - ini[3]
        Q2Pt_dis = mov[4] - ini[4]

        return np.array([Y_dis, Z_dis, Snp_dis, Tgl_dis, Q2Pt_dis],dtype=float)
    
    def normalize_vector(self,arr):

        return arr/self.NormArr


    def __getitem__(self,idx,fVecs=False):

        self.tpcMov.GetEntry(idx)   # we follow mov indexing and match the counter to ini
        self.__match_tracks()


        #print("mov count",self.tpcMov.counter)
        #print("ini count",self.tpcIni.counter)
        if self.tpcMov.counter!=self.tpcIni.counter:
            print("Mov",self.tpcMov.counter)
            print("Ini",self.tpcIni.counter)
            print("Tracks are matched incorrectly, exiting...")
            sys.exit(1)

        mov_vec, mov_clX, mov_clY, mov_clZ, dz = self.__movConstruct()

        # add clX min/max # 
        # rescale perhaps
        iniX, iniAlpha, ini_vec, ini_clX, ini_clY, ini_clZ, ini_clSector, ini_clRow = self.__iniConstruct()
        


        xDist = np.array(self._getDistortionEffects(mov_clX,ini_clX)) / self.ndimTPC
        yDist = np.array(self._getDistortionEffects(mov_clY,ini_clY)) / self.ndimTPC
        zDist = np.array(self._getDistortionEffects(mov_clZ,ini_clZ)) / self.ndimTPC
        
        if not self.transform:
            # ini_clSector = self._padForClusters(ini_clSector)
            # ini_clRow = self._padForClusters(ini_clRow) 

            xDist = self._padForClusters(xDist)
            yDist = self._padForClusters(yDist)
            zDist = self._padForClusters(zDist)
        else:
            if self.config is not None:
                idx_sel = select_tpc_clusters_idx(self.config.DATA_PARAMS.TPC_SETTINGS,len(xDist)-1)
            else:
                idx_sel = select_tpc_clusters_idx(config.DATA_PARAMS.TPC_SETTINGS,len(xDist)-1)

            # ini_clSector = ini_clSector[idx_sel]
            # ini_clRow = ini_clRow[idx_sel]
            xDist = xDist[idx_sel]
            yDist = yDist[idx_sel]
            zDist = zDist[idx_sel]

            #coordinate select
            ini_clZn = torch.tensor(ini_clZ)[idx_sel].float() / self.ndimTPC
            

        #concatenating everything (easier to implement in O2)
        input_vector = np.concatenate((ini_vec, dz, xDist, yDist, zDist)) # ,ini_clSector, ini_clRow))
        

        np_target = self._create_target(ini_vec,mov_vec,dz)

        #convert to tensor
        input_pt = torch.from_numpy(input_vector).float()
        input_pt = torch.cat((input_pt,ini_clZn))
        input_pt = self._checkVectorlen_(input_pt)

        target_pt = torch.from_numpy(np_target).float()

        if not fVecs:
            return input_pt, target_pt
        else:
            # return input_pt, target_pt, ini_vec, mov_vec, np.array(ini_clX)[idx_sel], np.array(ini_clY)[idx_sel], ini_clZ.numpy()*self.ndimTPC, np.array(mov_clX)[idx_sel], np.array(mov_clY)[idx_sel], np.array(mov_clZ)[idx_sel],np.array(ini_clSector)[idx_sel], np.array(ini_clRow)[idx_sel]
            return input_pt, target_pt, ini_vec, mov_vec, ini_clX, ini_clY, ini_clZ, mov_clX, mov_clY, mov_clZ,ini_clSector, ini_clRow, idx_sel
    

    def __len__(self):
        return self.EntriesMov


#IterableDataset
class iterTPCTreeCluster(IterableDataset):


    # def __init__(self, file,start,end,transform=False,conf=None):
    def __init__(self, file,transform=False,conf=None):

        self._file = file

        self.tpcIni = self._file.Get("tpcIni")
        self.tpcMov = self._file.Get("tpcMov")
        # tree_key tpcIni has key: iniTrackRef
        # tree_key tpcMov has key: movTrackRef

        self.EntriesIni = self.tpcIni.GetEntries()
        self.EntriesMov = self.tpcMov.GetEntries() 

        if conf.DATA_PARAMS.LIMIT_SET:
            self.EntriesMov = conf.DATA_PARAMS.NSAMPLES



        self.tpcMaxRow = 159 # 159 rows/max number of tpc clusters for padding
        self.ndimTPC = 250
        self.nKalmanFits = 6

        self.transform=transform


        if conf is not None:
            self.config= conf

        clusters = self.config.DATA_PARAMS.TPC_SETTINGS.TPC_CLUSTERS
        #removed X,Alpha..
        self.__shape = 5 + (clusters*3) + clusters + 1 # 7 ini params, clx,cly,clz, ini_clz, dz -- no more ,sector,row

        self.NormArr = np.array([250,250, 1, 5, 40])

        # self.start = start
        # self.end = end


    def _padForClusters(self,array):
        return np.pad(array,(0,self.tpcMaxRow-len(array)),"constant")

    def _shape(self):
        return self.__shape


    def __iniConstruct(self,):

        #construct ini vector
        ini_clSector = np.array(self.tpcIni.clSector)
        ini_clRow = np.array(self.tpcIni.clRow)

        iniX = self.tpcIni.iniTrackRef.getX()

        iniAlpha = self.tpcIni.iniTrackRef.getAlpha()

        iniY = self.tpcIni.iniTrackRef.getY()
        iniZ = self.tpcIni.iniTrackRef.getZ()
        iniSnp = self.tpcIni.iniTrackRef.getSnp()
        iniTgl = self.tpcIni.iniTrackRef.getTgl()
        iniQ2Pt = self.tpcIni.iniTrackRef.getQ2Pt()

        #ini toc clusters
        ini_clX = self.tpcIni.clX
        ini_clY = self.tpcIni.clY
        ini_clZ = self.tpcIni.clZ

        #ini_counter = self.tpcIni.counter
        
        ini_vec = np.array([iniY, iniZ, iniSnp, iniTgl, iniQ2Pt])
        ini_vec = self.normalize_vector(ini_vec)
        # X Alpha Y Z Snp Lambda q2 x y z sector row
        return iniX, iniAlpha, ini_vec, ini_clX, ini_clY, ini_clZ, ini_clSector, ini_clRow

    def __movConstruct(self):

        #construct mov vector or rather target
        MovY = self.tpcMov.movTrackRef.getY()
        MovZ = self.tpcMov.movTrackRef.getZ()
        MovSnp = self.tpcMov.movTrackRef.getSnp()
        MovTgl = self.tpcMov.movTrackRef.getTgl()
        MovQ2Pt = self.tpcMov.movTrackRef.getQ2Pt()

        
        #np_target = np.array([ MovY, MovZ]) 
        mov_vec = np.array([MovY, MovZ, MovSnp, MovTgl, MovQ2Pt])
        mov_vec = self.normalize_vector(mov_vec)
        #construct moved tpc clusters
        mov_clX = self.tpcMov.clX
        mov_clY = self.tpcMov.clY
        mov_clZ = self.tpcMov.clZ
        dz = np.array([self.tpcMov.dz]) / self.ndimTPC
        # imposedTB = np.array([self.tpcMov.imposedTB])

        # n_copy = self.tpcMov.copy
        # maxCopy = self.tpcMov.maxCopy

        # mov_counter = self.tpcMov.counter
        # Y Z Snp Lambda q2pt
        return mov_vec, mov_clX, mov_clY, mov_clZ, dz, #imposedTB#, mov_counter, n_copy, maxCopy

    def __match_tracks(self):

        counter = self.tpcMov.counter
        # n_copy = self.tpcMov.copy
        # maxCopy = self.tpcMov.maxCopy

        
        self.tpcIni.GetEntry(counter)


    def _getDistortionEffects(self,arr1,arr2):
        diff = list(map(operator.sub, arr1, arr2))
        return diff

    def _checkVectorlen_(self,array):

        if len(array) != self.__shape:
            # return np.pad(array,(0,self.__shape-len(array)),"constant")
            # return F.pad(array, (0,self.__shape-len(array)), "constant", 0)
            return F.pad(array, (array + self.__shape+10-len(array)), "constant", 0)
        else:
            return array

    def _create_target(self,ini,mov,dz):
        
        Y_dis = mov[0] - ini[0]
        Z_dis = mov[1] + dz - ini[1]
        Snp_dis = mov[2] - ini[2]
        Tgl_dis = mov[3] - ini[3]
        Q2Pt_dis = mov[4] - ini[4]

        return np.array([Y_dis, Z_dis, Snp_dis, Tgl_dis, Q2Pt_dis],dtype=float)
    
    def normalize_vector(self,arr):

        return arr/self.NormArr


    def __iter__(self):

        for idx in range(self.EntriesMov):

            self.tpcMov.GetEntry(idx)   # we follow mov indexing and match the counter to ini
            self.__match_tracks()


            #print("mov count",self.tpcMov.counter)
            #print("ini count",self.tpcIni.counter)
            if self.tpcMov.counter!=self.tpcIni.counter:
                print("Mov",self.tpcMov.counter)
                print("Ini",self.tpcIni.counter)
                print("Tracks are matched incorrectly, exiting...")
                sys.exit(1)

            mov_vec, mov_clX, mov_clY, mov_clZ, dz = self.__movConstruct()

            # add clX min/max # 
            # rescale perhaps
            iniX, iniAlpha, ini_vec, ini_clX, ini_clY, ini_clZ, ini_clSector, ini_clRow = self.__iniConstruct()
            


            xDist = np.array(self._getDistortionEffects(mov_clX,ini_clX)) / self.ndimTPC
            yDist = np.array(self._getDistortionEffects(mov_clY,ini_clY)) / self.ndimTPC
            zDist = np.array(self._getDistortionEffects(mov_clZ,ini_clZ)) / self.ndimTPC
            
            if not self.transform:
                # ini_clSector = self._padForClusters(ini_clSector)
                # ini_clRow = self._padForClusters(ini_clRow) 

                xDist = self._padForClusters(xDist)
                yDist = self._padForClusters(yDist)
                zDist = self._padForClusters(zDist)
            else:
                if self.config is not None:
                    idx_sel = select_tpc_clusters_idx(self.config.DATA_PARAMS.TPC_SETTINGS,len(xDist)-1)
                else:
                    idx_sel = select_tpc_clusters_idx(config.DATA_PARAMS.TPC_SETTINGS,len(xDist)-1)

                # ini_clSector = ini_clSector[idx_sel]
                # ini_clRow = ini_clRow[idx_sel]
                xDist = xDist[idx_sel]
                yDist = yDist[idx_sel]
                zDist = zDist[idx_sel]

                #coordinate select
                ini_clZ = torch.tensor(ini_clZ)[idx_sel].float() / self.ndimTPC
                

                

            #concatenating everything (easier to implement in O2)
            input_vector = np.concatenate((ini_vec, dz, xDist, yDist, zDist)) # ,ini_clSector, ini_clRow))
            

            np_target = self._create_target(ini_vec,mov_vec,dz)

            #convert to tensor
            input_pt = torch.from_numpy(input_vector).float()
            input_pt = torch.cat((input_pt,ini_clZ))
            input_pt = self._checkVectorlen_(input_pt)

            target_pt = torch.from_numpy(np_target).float()

            
            yield input_pt, target_pt
    

    def __len__(self):
        return self.EntriesMov

class MyTest(Dataset):
    def __init__(self, file):

        self._file = file

        self.tpcMov = self._file.Get("tpcMov")


    def __getitem__(self,idx,vecs=False):

        self.tpcMov.GetEntry(idx)   # we follow mov indexing and match the counter to ini
        return self.tpcMov.movTrackRef.getY()

    def __len__(self):
        return self.tpcMov.GetEntries()
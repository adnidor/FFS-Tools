#!/usr/bin/python3

###########################################################################################
#                                                                                         #
#  class_ffMeshNet.py                                                                     #
#                                                                                         #
#  Combining and analysing Data from Nodes and Gateways to find Mesh-Clouds.              #
#                                                                                         #
#                                                                                         #
#  Needed Python Classes:                                                                 #
#                                                                                         #
#      class_ffNodeInfo     -> Node Names and Information                                 #
#      class_ffGatewayInfo  -> Keys and Segment Information                               #
#                                                                                         #
###########################################################################################
#                                                                                         #
#  Copyright (c) 2017-2018, Roland Volkmann <roland.volkmann@t-online.de>                 #
#  All rights reserved.                                                                   #
#                                                                                         #
#  Redistribution and use in source and binary forms, with or without                     #
#  modification, are permitted provided that the following conditions are met:            #
#    1. Redistributions of source code must retain the above copyright notice,            #
#       this list of conditions and the following disclaimer.                             #
#    2. Redistributions in binary form must reproduce the above copyright notice,         #
#       this list of conditions and the following disclaimer in the documentation         #
#       and/or other materials provided with the distribution.                            #
#                                                                                         #
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"            #
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE              #
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE         #
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE           #
#  FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL             #
#  DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR             #
#  SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER             #
#  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,          #
#  OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE          #
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.                   #
#                                                                                         #
###########################################################################################

import os
import subprocess
import time
import datetime
import fcntl
import re

from class_ffNodeInfo import *
from class_ffGatewayInfo import *



#-------------------------------------------------------------
# Global Constants
#-------------------------------------------------------------

StatFileName   = 'SegStatistics.json'

MaxStatisticsData  = 12 * 24 * 7    # 1 Week wit Data all 5 Minutes

NODETYPE_UNKNOWN       = 0
NODETYPE_LEGACY        = 1
NODETYPE_SEGMENT_LIST  = 2
NODETYPE_DNS_SEGASSIGN = 3
NODETYPE_MTU_1340      = 4



class ffMeshNet:

    #==========================================================================
    # Constructor
    #==========================================================================
    def __init__(self,NodeInfos,GwInfos):

        # public Attributes
        self.Alerts          = []       # List of  Alert-Messages
        self.AnalyseOnly     = False    # Blocking active Actions due to inkonsistent Data

        # private Attributes
        self.__NodeInfos = NodeInfos
        self.__GwInfos   = GwInfos

        self.__MeshCloudDict  = {}      # Dictionary of Mesh-Clouds with List of Member-Nodes
        self.__SegmentDict    = {}      # Segment Data: { 'Nodes','Clients','Uplinks' }
        self.__NodeMoveDict   = {}      # Git Moves of Nodes from one Segment to another

        # Initializations
        self.__CheckConsistency()

        return



    #-----------------------------------------------------------------------
    # private function "__alert"
    #
    #   Store and print Message for Alert
    #
    #-----------------------------------------------------------------------
    def __alert(self,Message):

        self.Alerts.append(Message)
        print(Message)
        return



    #-----------------------------------------------------------------------
    # private function "__AddNeighbour2Cloud"
    #
    #   Add Nodes to Mesh-Cloud-List (recursive)
    #
    # MeshCloudDict[CloudID] -> List of Nodes in Mesh-Cloud
    #-----------------------------------------------------------------------
    def __AddNeighbour2Cloud(self,CloudID,ffNeighbourMAC):

        if self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Status'] != '?' and ffNeighbourMAC not in self.__MeshCloudDict[CloudID]['CloudMembers']:

            if self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['InCloud'] is None:
                self.__MeshCloudDict[CloudID]['NumClients'] += self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Clients']
                self.__MeshCloudDict[CloudID]['CloudMembers'].append(ffNeighbourMAC)
                self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['InCloud'] = CloudID

                if self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['GluonType'] < self.__MeshCloudDict[CloudID]['GluonType'] and self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Status'] == 'V':
                    self.__MeshCloudDict[CloudID]['GluonType'] = self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['GluonType']
#                    if self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['GluonType'] < NODETYPE_DNS_SEGASSIGN:
#                        print('>>> GluonType:',ffNeighbourMAC,'=',self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Name'])

                for MeshMAC in self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Neighbours']:
                    if MeshMAC in self.__NodeInfos.MAC2NodeIDDict:
#                        print('+',Cloud,MAC2NodeIDDict[MeshMAC])
                        self.__AddNeighbour2Cloud(CloudID,self.__NodeInfos.MAC2NodeIDDict[MeshMAC])
                    else:
                        print('!! Unknown Neighbour:',self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Segment'],'-',ffNeighbourMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Name']+'\' ->',MeshMAC)
            elif self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['InCloud'] == CloudID:
                print('!! Cloud inconsistent:',CloudID,'-',ffNeighbourMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['Name']+'\' ->',self.__MeshCloudDict[CloudID]['CloudMembers'])
            else:
                # Node is already part of another Mesh Cloud -> merge Clouds
                oldCloudID = self.__NodeInfos.ffNodeDict[ffNeighbourMAC]['InCloud']
    #            print('++ Merging Clouds:',ffNeighbourMAC,'= \''+ffNodeDict[ffNeighbourMAC]['Name']+'\'',oldCloudID,'->',CloudID)

                self.__MeshCloudDict[CloudID]['NumClients']   += self.__MeshCloudDict[oldCloudID]['NumClients']
                self.__MeshCloudDict[CloudID]['CloudMembers'] += self.__MeshCloudDict[oldCloudID]['CloudMembers']

                if self.__MeshCloudDict[oldCloudID]['GluonType'] < self.__MeshCloudDict[CloudID]['GluonType']:
                    self.__MeshCloudDict[CloudID]['GluonType'] = self.__MeshCloudDict[oldCloudID]['GluonType']

                for ffNodeMAC in self.__NodeInfos.ffNodeDict.keys():
                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['InCloud'] == oldCloudID:
                        self.__NodeInfos.ffNodeDict[ffNodeMAC]['InCloud'] = CloudID

                del self.__MeshCloudDict[oldCloudID]

        return



    #-----------------------------------------------------------------------
    # private function "__CreateMeshCloudList"
    #
    #   Create Mesh-Cloud-List
    #
    # MeshCloudDict[CloudID] -> List of Nodes in Mesh-Cloud
    #-----------------------------------------------------------------------
    def __CreateMeshCloudList(self):

        print('\nCreate Mesh Cloud List ...')
        TotalNodes = 0
        TotalClients = 0

        for ffNodeMAC in self.__NodeInfos.ffNodeDict.keys():
            if ((self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] != '?' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['InCloud'] is None) and
                (len(self.__NodeInfos.ffNodeDict[ffNodeMAC]['Neighbours']) > 0)):

                self.__MeshCloudDict[ffNodeMAC] = {
                    'NumClients': 0,
                    'GluonType': 99,
                    'CloudMembers': [],
                    'CloudSegment': None
                }

                self.__AddNeighbour2Cloud(ffNodeMAC,ffNodeMAC)

                if len(self.__MeshCloudDict[ffNodeMAC]['CloudMembers']) < 2:
                    print('++ Single-Node Cloud:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'],'-',ffNodeMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']+'\'')
                    self.__NodeInfos.ffNodeDict[ffNodeMAC]['InCloud'] = None
                    del self.__MeshCloudDict[ffNodeMAC]
                else:
                    TotalNodes   += len(self.__MeshCloudDict[ffNodeMAC]['CloudMembers'])
                    TotalClients += self.__MeshCloudDict[ffNodeMAC]['NumClients']

        print('... Number of Clouds / Nodes / Clients:',len(self.__MeshCloudDict),'/',TotalNodes,'/',TotalClients)
        print()
        return



    #-----------------------------------------------------------------------
    # private function "__MarkNodesInCloudForMove"
    #
    #   Move Nodes of Meshcloud to other Segement
    #
    #-----------------------------------------------------------------------
    def __MarkNodesInCloudForMove(self,CloudID,TargetSeg):

        for ffNodeMAC in self.__MeshCloudDict[CloudID]['CloudMembers']:
            if self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] != '':
                if int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]) != TargetSeg:
                    if ffNodeMAC in self.__NodeMoveDict:
                        print('!! Multiple Move:',ffNodeMAC,'->',TargetSeg)

                    if TargetSeg == 0:
                        print('!! No move to Legacy: %s/peers/%s\n' % (self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'],self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile']) )
                    else:
                        self.__NodeMoveDict[ffNodeMAC] = TargetSeg
                        print('>> git mv %s/peers/%s vpn%02d/peers/  = \'%s\'\n' % ( self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'],self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile'],
                                                                                 TargetSeg,self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name'] ))

        return



    #-----------------------------------------------------------------------
    # private function "__GetCloudSegment"
    #
    #   Get common Segment of Nodes in Mesh Cloud
    #
    #-----------------------------------------------------------------------
    def __GetCloudSegment(self,DesiredSegDict,FixedSegDict):

        SegUptime = {}
        SegWeightDict = {}
        MaxWeight = 0
        TargetSeg = None    # Target where all nodes of this cloud must be
        MultiFixSegment = False

        if len(FixedSegDict) > 0:
            for Segment in FixedSegDict:
                for ffNodeMAC in FixedSegDict[Segment]:
                    if self.__NodeInfos.IsOnline(ffNodeMAC) and not MultiFixSegment:
                        if TargetSeg is None:
                            TargetSeg = Segment
                        elif Segment != TargetSeg:
                            MultiFixSegment = True

                            if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == 'V':
                                self.__alert('!! SHORTCUT with fixed Nodes in multiple Segments !!')
                                TargetSeg = None

            if MultiFixSegment:
                self.__alert('!! ALARM - Multiple Segments with fixed Nodes!')

            for Segment in FixedSegDict:
                print('   Seg.',Segment,'-> ',FixedSegDict[Segment])

        elif TargetSeg is None:
            TargetSeg = 0    # Default = keep current segment

            for Segment in DesiredSegDict:
                SegUptime[Segment] = 0.0
                SegWeightDict[Segment] = 0

                for ffNodeMAC in DesiredSegDict[Segment]:
                    if Segment <= 8 or self.__NodeInfos.ffNodeDict[ffNodeMAC]['GluonType'] >= NODETYPE_DNS_SEGASSIGN:
                        if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Uptime'] > SegUptime[Segment]:
                            SegUptime[Segment] = self.__NodeInfos.ffNodeDict[ffNodeMAC]['Uptime']

                        if self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'][:6] == 'manual':
                            SegWeightDict[Segment] += 10
                        elif self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][:3] == 'vpn':
                            SegWeightDict[Segment] += 4
                        else:
                            SegWeightDict[Segment] += 1

            for Segment in SegWeightDict:
                if SegWeightDict[Segment] > MaxWeight or (SegWeightDict[Segment] == MaxWeight and SegUptime[Segment] > SegUptime[TargetSeg]):
                    MaxWeight = SegWeightDict[Segment]
                    TargetSeg = Segment

        return TargetSeg



    #-----------------------------------------------------------------------
    # private function "__CheckMeshClouds"
    #
    #   Analysing Mesh Clouds for Segment Shortcuts
    #
    #-----------------------------------------------------------------------
    def __CheckMeshClouds(self):

        print('Checking Mesh-Clouds ...')

        for CloudID in self.__MeshCloudDict:
            DesiredSegDict = {}    # desired segments with number of nodes
            FixedSegDict   = {}    # segments with fixed nodes
            UplinkSegList  = []    # segments of uplink-nodes
            ActiveSegList  = []    # really used segments
            isOnline       = False

            #---------- Analysing used segments with their nodes ----------
            for ffNodeMAC in self.__MeshCloudDict[CloudID]['CloudMembers']:
                VpnSeg = None

                if self.__NodeInfos.IsOnline(ffNodeMAC):
                    isOnline = True

                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] not in ActiveSegList:
                        ActiveSegList.append(self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'])

                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == 'V' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][:3] == 'vpn':
                        VpnSeg = int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:])

                        if VpnSeg not in UplinkSegList:
                            UplinkSegList.append(VpnSeg)

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'][:6] == 'manual' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][:3] == 'vpn':
                    self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] = int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:])

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] is not None:
                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] not in DesiredSegDict:
                        DesiredSegDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg']] = [ffNodeMAC]
                    else:
                        DesiredSegDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg']].append(ffNodeMAC)

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'][:3] == 'fix':  # Node cannot be moved!
                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] not in FixedSegDict:
                        FixedSegDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment']] = [ffNodeMAC]
                    else:
                        FixedSegDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment']].append(ffNodeMAC)

            #---------- Actions depending of situation in cloud ----------
            CloudSegment = self.__GetCloudSegment(DesiredSegDict,FixedSegDict)

            if len(UplinkSegList) > 1 or CloudSegment is None:
                self.__alert('!! Shortcut detected !!!')

                if CloudSegment is None:
                    self.__alert('!! Shortcut cannot be corrected !!')
                    self.AnalyseOnly = True
                else:
                    self.__MarkNodesInCloudForMove(CloudID,CloudSegment)
                    self.__alert('** Shortcut will be corrected ...')
                    print(self.__MeshCloudDict[CloudID]['CloudMembers'])
                    print()

            elif len(UplinkSegList) == 0 and isOnline:
                print('++ Cloud seems to be w/o VPN Uplink(s):',self.__MeshCloudDict[CloudID]['CloudMembers'])
                CheckSegList = ActiveSegList

                for DestSeg in DesiredSegDict:
                    if DestSeg not in CheckSegList:
                        CheckSegList.append(DestSeg)

                UplinkList = self.__NodeInfos.GetUplinkList(self.__MeshCloudDict[CloudID]['CloudMembers'],CheckSegList)
                print('>> Uplink(s) found by Batman:',UplinkList)

            else:
                if len(FixedSegDict) > 0:
                    print('++ Fixed Cloud:',self.__MeshCloudDict[CloudID]['CloudMembers'])
                elif CloudSegment == 0:
                    CloudSegment = UplinkSegList[0]    # keep current segment

                self.__MarkNodesInCloudForMove(CloudID,CloudSegment)    # ensure all Nodes be in the correct segment

            self.__MeshCloudDict[CloudID]['CloudSegment'] = CloudSegment

        print('... done.\n')
        return



    #-----------------------------------------------------------------------
    # private function "__CheckSingleNodes"
    #
    #   Check if Node is in correct Segment
    #
    #-----------------------------------------------------------------------
    def __CheckSingleNodes(self):

        print('Checking Single Nodes ...')

        for ffNodeMAC in self.__NodeInfos.ffNodeDict.keys():
            if ((self.__NodeInfos.ffNodeDict[ffNodeMAC]['InCloud'] is None and self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] != '?') and
                (self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][:3] == 'vpn' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['GluonType'] >= NODETYPE_SEGMENT_LIST) and
                (int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]) <= 64)):

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'][:4] == 'auto' or self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'][:4] == 'fix ':
                    TargetSeg = self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg']

                    if TargetSeg is not None:
                        if TargetSeg <= 8 or self.__NodeInfos.ffNodeDict[ffNodeMAC]['GluonType'] >= NODETYPE_DNS_SEGASSIGN:
                            if int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]) != TargetSeg:
                                if ffNodeMAC in self.__NodeMoveDict:
                                    print('!! Multiple Move:',ffNodeMAC,'->',TargetSeg)

                                self.__NodeMoveDict[ffNodeMAC] = TargetSeg
                                print('>> git mv %s/peers/%s vpn%02d/peers/  = \'%s\'' % (self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'],self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile'],
                                                                                      TargetSeg,self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name'] ))

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == ' ':
                    print('++ Node seems to be w/o VPN Uplink:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'],'/',ffNodeMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']+'\'')

            elif ((self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == '?' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] == 999) and
                  (self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] != '' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile'] != '')):
                self.__NodeMoveDict[ffNodeMAC] = 999    # kill this Node

        print('... done.\n')
        return



    #-----------------------------------------------------------------------
    # private function "CheckConsistency"
    #
    #
    #-----------------------------------------------------------------------
    def __CheckConsistency(self):

        print('Checking Consistency of Data ...')

        for ffNodeMAC in self.__NodeInfos.ffNodeDict.keys():
            if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] != '?':

                if self.__NodeInfos.IsOnline(ffNodeMAC) and self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] is None:
                    print('!! Segment is None:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'],ffNodeMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']+'\'')

                if self.__NodeInfos.IsOnline(ffNodeMAC) and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] != '' and int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]) != self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment']:
                    print('!! KeyDir <> Segment:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'],ffNodeMAC,'=',self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'],'<>',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'])

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == 'V' and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] == '':
                    print('!! Uplink w/o Key:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'],ffNodeMAC,'= \''+self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']+'\'')
                    self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] = ' '

                if ((self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] is not None and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] != '') and
                    (self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] != int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]) and self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'] == 'auto')):
                    print('++ Wrong Segment:    ',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'],ffNodeMAC,'=',int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:]),'->',self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'],self.__NodeInfos.ffNodeDict[ffNodeMAC]['SegMode'])

                if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] is None and self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg'] is not None:
                    self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] = self.__NodeInfos.ffNodeDict[ffNodeMAC]['DestSeg']
                elif self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] is None and self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'] != '':
                    self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment'] = int(self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyDir'][3:])


                #---------- calculate segment statistics ----------
                if self.__NodeInfos.IsOnline(ffNodeMAC):
                    ffSeg = self.__NodeInfos.ffNodeDict[ffNodeMAC]['Segment']

                    if ffSeg in self.__GwInfos.Segments():
                        if not ffSeg in self.__SegmentDict:
                            self.__SegmentDict[ffSeg] = { 'Nodes':0, 'Clients':0, 'Uplinks':0 }

                        self.__SegmentDict[ffSeg]['Nodes'] += 1
                        self.__SegmentDict[ffSeg]['Clients'] += self.__NodeInfos.ffNodeDict[ffNodeMAC]['Clients']

                        if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'] == 'V':
                            self.__SegmentDict[ffSeg]['Uplinks'] += 1
                    else:
                        print('>>> Bad Segment:   ',self.__NodeInfos.ffNodeDict[ffNodeMAC]['Status'],ffNodeMAC,'=',ffSeg)

                    if self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile'] != '':
                        if self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name'].strip().lower() != self.__GwInfos.FastdKeyDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile']]['PeerName'].strip().lower():
                            print('++ Hostname Mismatch:',self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile'],'->','\''+self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']+'\'',
                                  '<-','\''+self.__GwInfos.FastdKeyDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile']]['PeerName']+'\'')
                            self.__GwInfos.FastdKeyDict[self.__NodeInfos.ffNodeDict[ffNodeMAC]['KeyFile']]['PeerName'] = self.__NodeInfos.ffNodeDict[ffNodeMAC]['Name']

        print('... done.\n')
        return



    #==============================================================================
    # Method "CheckSegments"
    #
    #   Analysing Mesh Clouds for Segment Shortcuts
    #
    #==============================================================================
    def CheckSegments(self):

        self.__CreateMeshCloudList()
        self.__CheckMeshClouds()
        self.__CheckSingleNodes()

        return



    #==============================================================================
    # Method "GetMoveDict"
    #
    #   returns NodeMoveDict if there are nodes to be moved
    #
    #==============================================================================
    def GetMoveDict(self):

        if len(self.__NodeMoveDict) > 0:
            MoveData = self.__NodeMoveDict
        else:
            MoveData = None

        return MoveData



    #==============================================================================
    # Method "WriteMeshCloudList"
    #
    #   Write out Mesh Cloud List
    #==============================================================================
    def WriteMeshCloudList(self,FileName):

        print('Writing out Mesh Cloud List ...')

        NeighborOutFile = open(FileName, mode='w')
        NeighborOutFile.write('FFS-Mesh-Clouds on %s\n' % datetime.datetime.now())

        RegionDict = {}
        GluonMarker = [ '?', '%', '$', '$', ' ' ]
        TotalMeshingNodes = 0

        for CloudID in sorted(self.__MeshCloudDict):

            TotalNodes    = 0
            TotalClients  = 0
            TotalUplinks  = 0
            OldGluon      = 0
            CurrentSeg    = self.__MeshCloudDict[CloudID]['CloudSegment']
            CurrentVPN    = None
            CurrentRegion = None
            CurrentZIP    = None
            CurrentError  = ''

            NeighborOutFile.write('\n------------------------------------------------------------------------------------------------------------------\n')
            TotalMeshingNodes += len(self.__MeshCloudDict[CloudID]['CloudMembers'])

            for ffnb in sorted(self.__MeshCloudDict[CloudID]['CloudMembers']):
                CurrentError = ' '

                if self.__NodeInfos.ffNodeDict[ffnb]['Segment'] is None:
                    Segment = 99
                else:
                    Segment = self.__NodeInfos.ffNodeDict[ffnb]['Segment']

                    if CurrentSeg is None:
                        CurrentSeg = Segment
                    elif Segment != CurrentSeg:
#                        print('++ ERROR Segment:',ffnb,'=',CurrentSeg,'<>',Segment)
                        CurrentError = '!'

                    if CurrentRegion is None or CurrentRegion == '??':
                        CurrentRegion = self.__NodeInfos.ffNodeDict[ffnb]['Region']
                    elif self.__NodeInfos.ffNodeDict[ffnb]['Region'] != '??' and self.__NodeInfos.ffNodeDict[ffnb]['Region'] != CurrentRegion:
                        print('++ ERROR Region:',ffnb,'= \''+self.__NodeInfos.ffNodeDict[ffnb]['Name']+'\' ->',self.__NodeInfos.ffNodeDict[ffnb]['Region'],'<>',CurrentRegion)
                        CurrentError = '!'

                    if CurrentZIP is None:
                        CurrentZIP = self.__NodeInfos.ffNodeDict[ffnb]['ZIP']

                if CurrentError == ' ' and self.__NodeInfos.ffNodeDict[ffnb]['SegMode'] != 'auto':
                    CurrentError = '+'

                if CurrentError == ' ' and self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'] != '':
                    if ((self.__NodeInfos.ffNodeDict[ffnb]['Segment'] is not None and int(self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'][3:]) != self.__NodeInfos.ffNodeDict[ffnb]['Segment']) or
                        (self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'] is not None and self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'] != self.__NodeInfos.ffNodeDict[ffnb]['Segment'])):
                        print('++ ERROR Region:',self.__NodeInfos.ffNodeDict[ffnb]['Status'],ffnb,'= \''+self.__NodeInfos.ffNodeDict[ffnb]['Name']+'\' ->',
                              self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'],self.__NodeInfos.ffNodeDict[ffnb]['Segment'],'->',
                              self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'],self.__NodeInfos.ffNodeDict[ffnb]['SegMode'])
                        CurrentError = '>'

                if CurrentVPN is None and self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'] != '':
                    CurrentVPN = self.__NodeInfos.ffNodeDict[ffnb]['KeyDir']
                elif CurrentVPN is not None and self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'] != '' and self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'] != CurrentVPN:
                    print('++ ERROR KeyDir:',self.__NodeInfos.ffNodeDict[ffnb]['Status'],ffnb,'=',CurrentVPN,'<>',self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'])
                    CurrentError = '*'

                if CurrentError == ' ':
                    CurrentError = GluonMarker[self.__NodeInfos.ffNodeDict[ffnb]['GluonType']]

                NeighborOutFile.write('%s%s Seg.%02d [%3d] %s = %5s - %16s = \'%s\' (%s = %s) UpT = %d\n' % (CurrentError, self.__NodeInfos.ffNodeDict[ffnb]['Status'], Segment,
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['Clients'], ffnb, self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'],
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['KeyFile'], self.__NodeInfos.ffNodeDict[ffnb]['Name'],
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'], self.__NodeInfos.ffNodeDict[ffnb]['Region'],
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['Uptime']))
                if self.__NodeInfos.IsOnline(ffnb):
                    TotalNodes   += 1
                    TotalClients += self.__NodeInfos.ffNodeDict[ffnb]['Clients']

                if self.__NodeInfos.ffNodeDict[ffnb]['Status'] == 'V':
                    TotalUplinks += 1

                if self.__NodeInfos.ffNodeDict[ffnb]['GluonType'] < NODETYPE_MTU_1340:
                    OldGluon += 1

            NeighborOutFile.write('\n          Total Online-Nodes / Clients / Uplinks = %3d / %3d / %3d   (Seg. %02d)\n' % (TotalNodes,TotalClients,TotalUplinks,CurrentSeg))

            for ffnb in self.__MeshCloudDict[CloudID]['CloudMembers']:
                self.__NodeInfos.ffNodeDict[ffnb]['Segment'] = CurrentSeg
                self.__NodeInfos.ffNodeDict[ffnb]['Region']  = CurrentRegion
                self.__NodeInfos.ffNodeDict[ffnb]['ZIP']     = CurrentZIP

            if CurrentRegion is None:
                CurrentRegion = '***'

            if CurrentRegion not in RegionDict:
                RegionDict[CurrentRegion] = { 'Nodes':TotalNodes, 'Clients':TotalClients, 'OldGluon':OldGluon, 'Segment':CurrentSeg }
            else:
                RegionDict[CurrentRegion]['Nodes']    += TotalNodes
                RegionDict[CurrentRegion]['Clients']  += TotalClients
                RegionDict[CurrentRegion]['OldGluon'] += OldGluon

        print('\nSum: %d Clouds with %d Nodes\n' % (len(self.__MeshCloudDict),TotalMeshingNodes))
        NeighborOutFile.write('\nSum: %d Clouds with %d Nodes\n' % (len(self.__MeshCloudDict),TotalMeshingNodes))

        print('\nWriting out Single Nodes ...')

        NeighborOutFile.write('\n\n########################################################################\n\n')
        NeighborOutFile.write('Single Nodes:\n\n')

        for ffnb in sorted(self.__NodeInfos.ffNodeDict.keys()):
            if self.__NodeInfos.ffNodeDict[ffnb]['InCloud'] is None and self.__NodeInfos.IsOnline(ffnb) and self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'] != '':

                CurrentError = ' '

                if self.__NodeInfos.ffNodeDict[ffnb]['SegMode'] != 'auto':
                    CurrentError = '+'

                elif self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'] is not None and self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'] != int(self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'][3:]):
                    print('++ ERROR Region:',self.__NodeInfos.ffNodeDict[ffnb]['Status'],ffnb,self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'],
                          self.__NodeInfos.ffNodeDict[ffnb]['Segment'],'->',self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'],self.__NodeInfos.ffNodeDict[ffnb]['SegMode'])

                    CurrentError = '>'

                if self.__NodeInfos.ffNodeDict[ffnb]['Segment'] is None:
                    Segment = 99
                else:
                    Segment = self.__NodeInfos.ffNodeDict[ffnb]['Segment']

                if CurrentError == ' ':
                    CurrentError = GluonMarker[self.__NodeInfos.ffNodeDict[ffnb]['GluonType']]

                NeighborOutFile.write('%s%s Seg.%02d [%3d] %s = %5s - %16s = \'%s\' (%s = %s) UpT = %d\n' % (CurrentError, self.__NodeInfos.ffNodeDict[ffnb]['Status'],
                                                                                                Segment,self.__NodeInfos.ffNodeDict[ffnb]['Clients'], ffnb,
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['KeyDir'], self.__NodeInfos.ffNodeDict[ffnb]['KeyFile'],
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['Name'], self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'],
                                                                                                self.__NodeInfos.ffNodeDict[ffnb]['Region'], self.__NodeInfos.ffNodeDict[ffnb]['Uptime']))
                TotalNodes   += 1
                TotalClients += self.__NodeInfos.ffNodeDict[ffnb]['Clients']

                Region = self.__NodeInfos.ffNodeDict[ffnb]['Region']

                if Region not in RegionDict:
#                    RegionDict[Region] = { 'Nodes':1, 'Clients':self.__NodeInfos.ffNodeDict[ffnb]['Clients'], 'OldGluon':0, 'Segment':self.__NodeInfos.ffNodeDict[ffnb]['DestSeg'] }
                    RegionDict[Region] = { 'Nodes':1, 'Clients':self.__NodeInfos.ffNodeDict[ffnb]['Clients'], 'OldGluon':0, 'Segment':self.__NodeInfos.ffNodeDict[ffnb]['Segment'] }
                else:
                    RegionDict[Region]['Nodes']   += 1
                    RegionDict[Region]['Clients'] += self.__NodeInfos.ffNodeDict[ffnb]['Clients']

                if self.__NodeInfos.ffNodeDict[ffnb]['GluonType'] < NODETYPE_MTU_1340:
                    RegionDict[Region]['OldGluon'] += 1

        print('\nWrite out Statistics ...')

        NeighborOutFile.write('\n\n########################################################################\n\n')
        NeighborOutFile.write('Online-Nodes      / Clients / Sum:\n\n')

        TotalNodes   = 0
        TotalClients = 0
        TotalUplinks = 0

        for ffSeg in sorted(self.__SegmentDict):
            NeighborOutFile.write('Segment %02d: %5d / %5d / %5d\n' % (ffSeg, self.__SegmentDict[ffSeg]['Nodes'], self.__SegmentDict[ffSeg]['Clients'], self.__SegmentDict[ffSeg]['Nodes']+self.__SegmentDict[ffSeg]['Clients']))
            TotalNodes   += self.__SegmentDict[ffSeg]['Nodes']
            TotalClients += self.__SegmentDict[ffSeg]['Clients']
#            TotalUplinks += self.__SegmentDict[ffSeg]['Uplinks']


        NeighborOutFile.write('\n------------------------------------------------------------------------\n')
        NeighborOutFile.write('Totals:     %5d / %5d / %5d\n' % (TotalNodes, TotalClients, TotalNodes+TotalClients))


        NeighborOutFile.write('\n\n########################################################################\n\n')
        NeighborOutFile.write('Stress of Regions:\n\n')

        TotalNodes   = 0
        TotalClients = 0

        for Region in sorted(RegionDict):
            NeighborOutFile.write('%-32s: %4d + %4d = %4d  (Seg.%02d / old = %2d)\n' % (Region, RegionDict[Region]['Nodes'], RegionDict[Region]['Clients'], RegionDict[Region]['Nodes']+RegionDict[Region]['Clients'], RegionDict[Region]['Segment'], RegionDict[Region]['OldGluon']))
            TotalNodes   += RegionDict[Region]['Nodes']
            TotalClients += RegionDict[Region]['Clients']

        NeighborOutFile.write('\n------------------------------------------------------------------------\n')
        NeighborOutFile.write('Totals:     %5d / %5d / %5d\n' % (TotalNodes, TotalClients, TotalNodes+TotalClients))

        NeighborOutFile.close()
        print()
        return

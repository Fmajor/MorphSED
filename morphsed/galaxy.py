import ezgal
import pyprofit
from scipy.integrate import trapz
from astropy.convolution import convolve_fft
import numpy as np
from astropy.table import Table
from scipy.interpolate import interp1d
import sys
sys.path.append('/Users/liruancun/Works/GitHub/MorphSED/morphsed/')
from sed_interp import sed_bc03,get_AGN_SED

'''
"allbands":
'acs_f625w', '4star_m_j2', 'wfc3_f555w', 'wfc3_f139m', 'acs_f475w', 'ukidss_h', 'ndwfs_r', '4star_m_j3', 'acs_f435w',
    'ch1', 'ndwfs_i', '4star_j', 'galex_nuv', 'wfc3_f606w', '4star_m_hlong', 'wfc3_f125w', 'newfirm_j', 'newfirm_ks',
    'sloan_z', 'wfc3_f140w', 'sloan_g', 'sloan_i', 'wfc3_f814w', 'sloan_u', 'wfc3_f775w', 'sloan_r', 'r', 'wise_ch1',
    '4star_m_hshort', 'i', '4star_ks', 'wfpc2_f450w', 'README', 'h', 'wfc3_f275w', '4star_h', 'ch3', 'ukidss_k',
    'wfc3_f218w', 'ch4', 'ukidss_y', '4star_m_j1', 'wfc3_f110w', 'ukidss_j', 'ch2', 'wfc3_f153m', 'acs_f606w', 'ndwfs_bw',
    'wfpc2_f814w', 'galex_fuv', 'wfc3_f225w', 'wfpc2_f675w', 'ks', 'acs_f555w', 'wfc3_f625w', 'wfc3_f127m', 'wfc3_f475w',
    'wfpc2_f555w', 'wfc3_f438w', 'wfc3_f105w', 'newfirm_h', 'wfc3_f160w', 'j', 'v', 'acs_f775w', 'wfpc2_f606w', 'wise_ch2',
    'acs_f814w', 'wfc3_f850lp', 'b', 'wise_ch3', 'wise_ch4', 'acs_f850lp'
'''

class switch(object):
    def __init__(self, value):
        self.value = value
        self.fall = False

    def __iter__(self):
        """Return the match method once, then stop"""
        yield self.match
        raise StopIteration

    def match(self, *args):
        """Indicate whether or not to enter a case suite"""
        if self.fall or not args:
            return True
        elif self.value in args: # changed for v1.5, see below
            self.fall = True
            return True
        else:
            return False

def IFU_to_img(IFU,wave,band,step=0.5):
    '''
    Transform a IFU data cube in to a 2D image

    IFU:   the input 3D array with z as the wavelength dimension
    wave:  1D array shows the sampled wavelength
    band:  choose one from "all bands"
    step:  float, wavelength accuracy to integrate flux
    filterpath = where the ezgal installed
    '''
    filterpath = '/Users/liruancun/Softwares/anaconda3/lib/python3.7/site-packages/ezgal/data/filters/'
    resp = Table.read(filterpath + band,format='ascii')
    filter_x=resp['col1']
    filter_y=resp['col2']
    tminx = np.max([np.min(filter_x),np.min(wave)])
    tmaxx = np.min([np.max(filter_x),np.max(wave)])
    interX = np.arange(tminx,tmaxx,step)
    f2=interp1d(filter_x,filter_y,bounds_error=False,fill_value=0.)
    ax=trapz(f2(interX),x=interX)
    nz,ny,nx = IFU.shape
    image = np.zeros((ny,nx))
    for loopy in range(ny):
        for loopx in range(nx):
            f1=interp1d(wave,IFU[:,loopy,loopx],bounds_error=False,fill_value=0.)
            tof=lambda x : f1(x)*f2(x)
            image[loopy][loopx] = trapz(tof(interX),x=interX)
    image /= ax
    return image

def Cal_map(r, type, paradic):
    for case in switch(type):
        if case('linear'):
            return paradic['b'] + paradic['k']*r
            break
        if case('exp'):
            return (paradic['in']-paradic['out'])*np.exp(-r/paradic['k'])+paradic['out']
            break
        if case():
            raise ValueError("Unidentified method for calculate age or Z map")

class Galaxy(object):
    '''
    the galaxy object
    with physical subcomponents and parameters
    '''
    def __init__(self,mass=1e9):
        '''
        galaxy object is initialed from a given mass
        '''
        self.mass = mass
        self.Nsub=0
        self.subCs = {}
        self.ageparams={}
        self.Zparams={}
        self.maglist = []
        self.imshape = None
        self.mass_map = {}
    def reset_mass(self,mass):
        '''
        reset the mass of a galaxy object
        '''
        self.mass = mass
    def add_subC(self,Pro_names,params,ageparam,Zparam):
        '''
        To add a subcomponent for a galaxy object

        Pro_names: the name of the profiles
        e.g. = "sersic" "coresersic" "brokenexp" "moffat" "ferrer" "king" "pointsource"

        params: a dictionary of the parameters for this subcomponent
        e.g. for sersic: {'xcen': 50.0, 'ycen': 50.0, 'frac': 0.704, 're': 10.0,
        'nser': 3.0, 'ang': -32.70422048691768, 'axrat': 1.0, 'box': 0.0, 'convolve': False}

        ageparam: a dictionary of the age dsitribution parameters for this subcomponent
        e.g. {'type': 'linear', 'paradic': {'k': -0.05, 'b': 9.0}}

        Zparam: a dictionary of the matallicity dsitribution parameters for this subcomponent
        e.g. {'type': 'linear', 'paradic': {'k': 0.0, 'b': 0.02}}
        '''
        params['mag']=params.pop("frac")
        params['mag'] = 10. - 2.5*np.log10(params['mag'])
        if Pro_names in self.subCs.keys():
            self.subCs[Pro_names].append(params)
            self.ageparams[Pro_names].append(ageparam)
            self.Zparams[Pro_names].append(Zparam)
        else:
            self.subCs.update({Pro_names : [params]})
            self.ageparams.update({Pro_names : [ageparam]})
            self.Zparams.update({Pro_names : [Zparam]})
            self.mass_map.update({Pro_names : []})
        #print (self.mass_map)
        self.maglist.append(params['mag'])
        #print (self.maglist)

    def generate_mass_map(self,shape,convolve_func):
        '''
        gemerate the mass distribution map for a galaxy object
        shape: return 2D image shape
        convolve_func: a 2D kernel if convolution is needed
        '''
        mags = np.array(self.maglist)
        magzero = 2.5*np.log10(self.mass/np.sum(np.power(10,mags/(-2.5))))
        profit_model = {'width':  shape[1],
                'height': shape[0],
                'magzero': magzero,
                'psf': convolve_func,
                'profiles': self.subCs
               }
        image, _ = pyprofit.make_model(profit_model)
        ny,nx=shape
        self.shape = shape
        image = np.zeros(shape,dtype=float)
        xaxis = np.arange(nx)
        yaxis = np.arange(ny)
        xmesh, ymesh = np.meshgrid(xaxis, yaxis)
        for key in self.subCs:
            self.mass_map[key]=[]
            for loop in range(len(self.subCs[key])):
                params = self.subCs[key][loop]
                profit_model = {'width':  nx,
                    'height': ny,
                    'magzero': magzero,
                    'psf': convolve_func,
                    'profiles': {key:[params]}
                   }
                mass_map, _ = pyprofit.make_model(profit_model)
                mass_map = np.array(mass_map)
                mass_map = np.array(mass_map.tolist())
                self.mass_map[key].append(mass_map)
                image += mass_map
                r = np.sqrt( (xmesh+0.5 - self.subCs[key][loop]['xcen'])**2. + (ymesh+0.5 - self.subCs[key][loop]['ycen'])**2.)
                self.ageparams[key][loop].update({'age_map' : Cal_map(r,self.ageparams[key][loop]['type'],self.ageparams[key][loop]['paradic'])})
                self.Zparams[key][loop].update({'Z_map' : Cal_map(r,self.Zparams[key][loop]['type'],self.Zparams[key][loop]['paradic'])})
        #print (self.Zparams)
        return image

    def generate_SED_IFU(self,shape,convolve_func,wavelength):
        '''
        gemerate the SED IFU for a galaxy object
        shape: return 2D spatial shape
        convolve_func: a 2D kernel if convolution is needed
        wavelength: 1D array, the wavelength sample
        '''
        ny = shape[0]
        nx = shape[1]
        mags = np.array(self.maglist)
        magzero = 2.5*np.log10(self.mass/np.sum(np.power(10,mags/(-2.5))))
        tot_IFU = np.zeros((len(wavelength),ny,nx))
        for key in self.subCs:
            for loop in range(len(self.subCs[key])):
                params = self.subCs[key][loop]
                profit_model = {'width':  nx,
                    'height': ny,
                    'magzero': magzero,
                    'psf': convolve_func,
                    'profiles': {key:[params]}
                   }
                mass_map, _ = pyprofit.make_model(profit_model)
                sub_IFU = np.zeros((len(wavelength),ny,nx))
                xaxis = np.arange(nx)
                yaxis = np.arange(ny)
                xmesh, ymesh = np.meshgrid(xaxis, yaxis)
                r = np.sqrt( (xmesh+0.5 - self.subCs[key][loop]['xcen'])**2. + (ymesh+0.5 - self.subCs[key][loop]['ycen'])**2.)
                age_map = Cal_map(r,self.ageparams[key][loop]['type'],self.ageparams[key][loop]['paradic'])
                Z_map = Cal_map(r,self.Zparams[key][loop]['type'],self.Zparams[key][loop]['paradic'])
                for loopy in range(ny):
                    for loopx in range(nx):
                        sub_IFU[:,loopy,loopx] = sed_bc03(wavelength, Z_map[loopy][loopx], age_map[loopy][loopx], np.log10(mass_map[loopy][loopx]))
                tot_IFU += sub_IFU

        return tot_IFU

    def generate_image(self,band,convolve_func,inte_step=10):
        filterpath = '/Users/liruancun/Softwares/anaconda3/lib/python3.7/site-packages/ezgal/data/filters/'
        resp = Table.read(filterpath + band,format='ascii')
        ny = self.shape[0]
        nx = self.shape[1]
        filter_x=resp['col1']
        filter_y=resp['col2']
        tminx = np.min(filter_x)
        tmaxx = np.max(filter_x)
        interX = np.linspace(tminx,tmaxx,100)
        f2=interp1d(filter_x,filter_y,bounds_error=False,fill_value=0.)
        ax=trapz(f2(interX),x=interX)
        r_grid = np.linspace(0.,np.sqrt(nx*ny/np.pi),inte_step)
        totalflux = np.zeros(self.shape,dtype=float)
        #print (r_grid)
        for key in self.subCs:
            for loop in range(len(self.subCs[key])):
                agelist = []
                fratio_age = []
                Zlist = []
                fratio_Z = []
                for loopr in range(inte_step):
                    r_age = Cal_map(r_grid[loopr],self.ageparams[key][loop]['type'],self.ageparams[key][loop]['paradic'])
                    r_Z = Cal_map(r_grid[loopr],self.Zparams[key][loop]['type'],self.Zparams[key][loop]['paradic'])
                    agelist.append(r_age)
                    Zlist.append(r_Z)
                    #print (interX,Zlist[0], r_age)
                    #print (agelist)
                    centerSED = sed_bc03(interX, Zlist[0], r_age, 0.)
                    flux = trapz(centerSED*f2(interX),x=interX)/ax
                    fratio_age.append(flux)
                    centerSED = sed_bc03(interX, r_Z, agelist[0], 0.)
                    flux = trapz(centerSED*f2(interX),x=interX)/ax
                    fratio_Z.append(flux)
                    if loopr == 0:
                        flux_band = flux
                fratio_age = np.array(fratio_age)/flux_band
                fratio_Z = np.array(fratio_Z)/flux_band
                #print (fratio_Z)
                f_age = np.interp(self.ageparams[key][loop]['age_map'],np.array(agelist),fratio_age)
                f_Z = np.interp(self.Zparams[key][loop]['Z_map'],np.array(Zlist),fratio_Z)
                #print (f_Z(self.Zparams[key][loop]['Z_map']))
                totalflux += flux_band*self.mass_map[key][loop]*f_age*f_Z
                #print (totalflux)
        return convolve_fft(totalflux,convolve_func)


    class AGN(object):
        '''
        the AGN object
        with physical subcomponents and parameters
        '''
        def __init__(self,logM_BH=8.,logLedd=-1.,astar=0.):
            '''
            galaxy object is initialed from a given mass
            '''
            self.logM_BH = logM_BH
            self.logLedd=logLedd
            self.astar = astar

        def generate_image(self, shape,band, convolve_func, psfparams, psftype='pointsource'):
            '''
            Parameters:
            shape: (y,x) of the output image

            band: band of the output image

            convolve_func: 2D array, the shape of empirical PSF

            {psftype: [psfparams]}: a dict, the point spread function
            eg.  {'pointsource': [{'xcen':50, 'ycen':50}]}     stands for a point sources which have same shape as the empirical PSF
                 {'moffat': [{'xcen':50, 'ycen':50, 'fwhm':3., 'con':'5.'}]}
            '''
            filterpath = '/Users/liruancun/Softwares/anaconda3/lib/python3.7/site-packages/ezgal/data/filters/'
            resp = Table.read(filterpath + band,format='ascii')
            ny = self.shape[0]
            nx = self.shape[1]
            filter_x=resp['col1']
            filter_y=resp['col2']
            tminx = np.min(filter_x)
            tmaxx = np.max(filter_x)
            interX = np.linspace(tminx,tmaxx,100)
            f2=interp1d(filter_x,filter_y,bounds_error=False,fill_value=0.)
            ax=trapz(f2(interX),x=interX)
            agnsed = get_AGN_SED(interX,self.logM_BH,self.logLedd,self.astar,1.)
            flux_band = trapz(agnsed*f2(interX),x=interX)/ax
            magzero = 18.
            mag = -2.5*np.log10(flux_band)+magzero
            psfparams.update('mag':mag)
            profit_model = {'width':  nx,
                'height': ny,
                'magzero': magzero,
                'psf': convolve_func,
                'profiles': {psftype:[psfparams]}
               }
            agn_map, _ = pyprofit.make_model(profit_model)
            return agn_map

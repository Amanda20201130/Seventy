import re
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from scipy.constants import physical_constants

#https://github.com/Chenzhiyong47/VASP

eV_to_hartree = physical_constants['electron volt-hartree relationship'][0]
bohr_to_m = physical_constants['Bohr radius'][0]
angstrom_to_bohr = bohr_to_m / 1e-10



pd.options.display.max_columns = None
pd.options.display.max_rows = None


# 能带的每一条路径 K 点数目
# 比如 KPOINTS 长这样的话要向下面这么设置：
"""
K-Path Generated by VASPKIT.
   80
Line-Mode
Reciprocal
   0.0000000000   0.0000000000   0.0000000000     G       
   0.5000000000   0.0000000000   0.0000000000     M              
 
   0.5000000000   0.0000000000   0.0000000000     M              
   0.3333333333   0.3333333333   0.0000000000     K              
 
   0.3333333333   0.3333333333   0.0000000000     K              
   0.0000000000   0.0000000000   0.0000000000     G 
"""
K_lists = [80, 80, 80, ]



class EffectiveMass:

    def __init__(self, num_sample_points=6):

        # 能带数据文件夹名字
        self.file_name = "BAND.dat"
        # K 点数目，能带条数
        self.K_number, self.bands_number = self.get_K_number_and_bands_number()

        if sum(K_lists) == self.K_number:

            # 能带的所有数据
            self.datas = pd.read_csv(self.file_name, comment="#", sep="\s+" , names=['K', 'bands']) 
            # 每一条能带的数据 (DataFrame 对象列表) 
            self.Bands = self.get_Bands()
            # 最低导带的下标，最高价带的下标
            self.CBM_index, self.VBM_index = self.get_VBM_CBM_index()["CBM"], self.get_VBM_CBM_index()["VBM"]
            
            # ：每一段路径的最高价带的能带数据
            # ： VBM 的 K 点，
            # ： VBM 的能带数据
            self.VBM_list_bands, self.VBM_kpoints, self.VBM_bands = self.split_bands_by_K_lists(self.Bands[self.VBM_index], K_lists)
            self.get_fitting_effective_mass_of_every_path(self.VBM_kpoints, self.VBM_bands, band_type="VBM", num_sample_points=num_sample_points)


            # ：每一段路径的最高价带的能带数据
            # ： CBM 的 K 点，
            # ： CBM 的能带数据
            self.CBM_list_bands, self.CBM_kpoints, self.CBM_bands = self.split_bands_by_K_lists(self.Bands[self.CBM_index], K_lists)
            self.get_fitting_effective_mass_of_every_path(self.CBM_kpoints, self.CBM_bands, band_type="CBM", num_sample_points=num_sample_points)

        else:
            print("输入的 K 点数目 和 能带数据文件不符合, 请检查 K_lists 的设置")


    def get_K_number_and_bands_number(self):
    
        nums = []
        
        with open(self.file_name, 'r') as f:
            next(f)
            nums = re.findall(r"\d+\.?\d*", f.readline())
            
        return (int(nums[0]), int(nums[1]))


    def get_Bands(self):

        Bands = []

        for i in range(self.bands_number):
            X = []
            Y = []
            for j in range(self.K_number):
                index = i * self.K_number + j
                X.append(self.datas.K[index])
                Y.append(self.datas.bands[index])
            
            # 创建 DF 对象
            temp = pd.DataFrame(np.array([X, Y]).T, columns=["K", "bands"])
            Bands.append(temp)

        return Bands



    def get_VBM_CBM_index(self):

        for i in range(self.bands_number - 1):
            # 减去费米能级的能带数据，价带小于 0 ，导带大于 0.
            # 判断第 i 条带所有能带值小于 0 且 第 i + 1 条带大于 0
            if ((self.Bands[i].bands < 0).all()) and  (self.Bands[i+1].bands > 0).all():
                CBM_index = i+1
                VBM_index = i
                break

        try:
            with open("./VBM", "w+") as f:
                print(self.Bands[VBM_index], file=f)

            with open("./CBM", "w+") as f:
                print(self.Bands[CBM_index], file=f)

            return {"CBM": CBM_index, "VBM": VBM_index}

        except:
            print("检查最高价带和最低导带是否重叠了，或者最高价带和最低导带越过了费米面")       

        
    def fit_effective_mass(self, kpoints, energies, parabolic=True):
    
        if parabolic:
            fit = np.polyfit(kpoints, energies, 2)
            c = 2 * fit[0]  # curvature therefore 2 * the exponent on the ^2 term
            
        else:
            # Use non parabolic description of the bands
            # 使用非抛物线拟合
            def f(x, alpha, d):
                top = np.sqrt(4 * alpha * d * x**2 + 1) - 1
                bot = 2 * alpha
                return top / bot

            # set boundaries for curve fitting: alpha > 1e-8
            # as alpha = 0 causes an error
            bounds = ((1e-8, -np.inf), (np.inf, np.inf))
            popt, _ = curve_fit(f, kpoints, energies, p0=[1., 1.],
                                bounds=bounds)
            c = 2 * popt[1]
            
        eff_mass = (angstrom_to_bohr**2 / eV_to_hartree) / c

        # print("系数： {}".format((angstrom_to_bohr**2 / eV_to_hartree)))
        
        return eff_mass

    """
    sons_band:
        K，bands 的 dataframe 对象
        
    kpoints:
        K 点的 list 对象

    energies:
        能带数值的 list 对象

    """
    # 按路径划分能带
    def split_bands_by_K_lists(self, band, K_lists):
        path_number = len(K_lists)
        sons_band = []
        kpoints = []
        energies = []
        start = 0
        last = 0
        
        for i in range(path_number):
            
            last = last + K_lists[i]
            temp = band[start: last]
            
            sons_band.append(temp)
            kpoints.append(temp["K"].tolist())
            energies.append(temp["bands"].tolist())
            
            start = last + 1
        
        return sons_band, kpoints, energies



    def get_fitting_effective_mass_of_every_path(self, kpoints, bands, band_type=None, num_sample_points=3):

        if band_type==None:
            print("Please set VBM or CBM")
            return
        
        len_bands = len(bands)
        
        if band_type=="VBM":
            for i in range(len_bands):
                temp_energy = bands[i]
                temp_kpoint = kpoints[i]
                len_temp_energy = len(temp_energy)
                max_temp_energy = max(temp_energy)
                
                
                # 最大值下标
                max_index = temp_energy.index(max_temp_energy)
                
                # 将能量和坐标移至 0 的位置
                temp_energy = (np.array(temp_energy) - max_temp_energy)
                temp_kpoint = (np.array(temp_kpoint) - temp_kpoint[max_index])
                
                
                # 收集数据
                if max_index - num_sample_points >= 0:
                    
                    start_id = max_index - num_sample_points
                    end_id = max_index + 1
                
                    energy_datas = temp_energy[start_id: end_id]
                    kpoint_datas = temp_kpoint[start_id: end_id]
                    
                    energy_datas = np.concatenate([ energy_datas[:-1], energy_datas[::-1] ])
                    kpoint_datas = np.concatenate([ kpoint_datas[:-1], -kpoint_datas[::-1] ])
                    
                elif max_index + num_sample_points <= len_temp_energy:
                    
                    start_id = max_index
                    end_id = max_index + num_sample_points + 1
                    
                    energy_datas = temp_energy[start_id: end_id]
                    kpoint_datas = temp_kpoint[start_id: end_id]
                    
                    energy_datas = np.concatenate([ energy_datas[::-1], energy_datas[1:] ])
                    kpoint_datas = np.concatenate([ -kpoint_datas[::-1], kpoint_datas[1:] ])
                    
                mass = self.fit_effective_mass(kpoint_datas, energy_datas)
                print("第 {ith_path} 条路径的 VBM 的有效质量： {mass: 6.5f} m0".format(ith_path=i+1, mass=mass))
                    
            
        elif band_type=="CBM":
            
            for i in range(len_bands):
                temp_energy = bands[i]
                temp_kpoint = kpoints[i]
                len_temp_energy = len(temp_energy)
                min_temp_energy = min(temp_energy)
                
                
                # 最大值下标
                min_index = temp_energy.index(min_temp_energy)
                
                # 将能量和坐标移至 0 的位置
                temp_energy = (np.array(temp_energy) - min_temp_energy)
                temp_kpoint = (np.array(temp_kpoint) - temp_kpoint[min_index])
                
                
                # 收集数据
                if min_index - num_sample_points >= 0:
                    
                    start_id = min_index - num_sample_points
                    end_id = min_index + 1
                
                    energy_datas = temp_energy[start_id: end_id]
                    kpoint_datas = temp_kpoint[start_id: end_id]
                    
                    energy_datas = np.concatenate([ energy_datas[:-1], energy_datas[::-1] ])
                    kpoint_datas = np.concatenate([ kpoint_datas[:-1], -kpoint_datas[::-1] ])
                    
                
                elif min_index + num_sample_points <= len_temp_energy:
                    
                    start_id = min_index
                    end_id = min_index + num_sample_points + 1
                    
                    energy_datas = temp_energy[start_id: end_id]
                    kpoint_datas = temp_kpoint[start_id: end_id]
                    
                    energy_datas = np.concatenate([ energy_datas[::-1], energy_datas[1:] ])
                    kpoint_datas = np.concatenate([ -kpoint_datas[::-1], kpoint_datas[1:] ])
            
                mass = self.fit_effective_mass(kpoint_datas, energy_datas)
                print("第 {ith_path} 条路径的 CBM 的有效质量： {mass: 6.5f} m0".format(ith_path=i+1, mass=mass))



    def __del__(self):

        print("......")


if __name__ == "__main__":

    Exa_1 = EffectiveMass()




from keras.models import Sequential
from keras.layers.core import Dense
from keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
from sklearn.utils import shuffle

import pandas as pd
import numpy as np
import itertools as it

import sys
import os
import json

# use molssi 
sys.path.insert(0, "../../../")
import molssi

input_obj = molssi.input_processor.InputProcessor("../input.dat")
mol = molssi.molecule.Molecule(input_obj.zmat_string)
geom_labels = mol.geom_parameters
data = pd.DataFrame(columns = geom_labels)

os.chdir("../PES_data")
ndirs = sum(os.path.isdir(d) for d in os.listdir("."))

def cartesian_grad_to_idm(grad):
    """
    Convert cartesian gradient to interatomic distance gradient 
    """
    mat = np.zeros((len(grad),len(grad)))
    for i,j in it.combinations(range(len(grad)),2):
        R = np.linalg.norm(grad[i]-grad[j])
        mat[i,j] = R
        mat[j,i] = mat[i,j]
    return mat

E = []
G = []
for i in range(1, ndirs+1):
    # get geometry data
    with open(str(i) + "/geom") as f:
        tmp = json.load(f) 
    new = []
    for l in geom_labels:
        new.append(tmp[l])
    # create row of dataframe for this geometry, energy
    df = pd.DataFrame([new], columns = geom_labels)
    path = str(i) + "/output.dat"
    # get output data (energies and/or gradients)
    output_obj = molssi.outputfile.OutputFile(path)
    energy = output_obj.extract_energy_with_regex("Final Energy:\s+(-\d+\.\d+)") 
    gradient = output_obj.extract_cartesian_gradient_with_cclib()
    #gradient = cartesian_grad_to_idm(gradient)
    gradient = gradient[1,2]
    data = data.append(df)
    E.append(energy)
    G.append(gradient)

os.chdir("../NNs")
data['Energy'] = E
data['Gradient'] = G

# we have 100 datapoints of geometry, energy pairs
# take one third for test, validate, train, sample each set evenly along the surface

test_x = data.iloc[1::3, :-2].values
test_e = data.iloc[1::3, -2].values
test_g = data.iloc[1::3, -1].values

valid_x = data.iloc[2::3, :-2].values
valid_e = data.iloc[2::3, -2].values
valid_g = data.iloc[2::3, -1].values

train_x = data.iloc[0::3, :-2].values
train_e = data.iloc[0::3, -2].values
train_g = data.iloc[0::3, -1].values


## scale the data
scaler = MinMaxScaler(feature_range=(-1,1))
test_x = scaler.fit_transform((test_x).reshape(-1,1))
# scaling the gradients causes the minimum energy to not correspond to the minimum gradient
test_e = scaler.fit_transform((test_e.reshape(-1,1)))
test_g = test_g.reshape(-1,1)
#test_g = scaler.fit_transform((test_g.reshape(-1,1)))
test_y = np.hstack((test_e, test_g))

train_x = scaler.fit_transform(train_x.reshape(-1,1))
train_e = scaler.fit_transform(train_e.reshape(-1,1))
train_g = train_g.reshape(-1,1)
#train_g = scaler.fit_transform(train_g.reshape(-1,1))
train_y = np.hstack((train_e, train_g))

valid_x = scaler.fit_transform(valid_x.reshape(-1,1))
valid_e = scaler.fit_transform(valid_e.reshape(-1,1))
valid_g = valid_g.reshape(-1,1)
#valid_g = scaler.fit_transform(valid_g.reshape(-1,1))
valid_y = np.hstack((valid_e, valid_g))
valid_set = tuple([valid_x, valid_y])

in_dim = train_x.shape[1]
out_dim = train_y.shape[1]

# train a fresh model 50 times. Save the best one.
models = []
MAE = []
for i in range(1):
    model = Sequential([
    Dense(units=100, input_shape=(1,), activation='softsign'),
    Dense(units=100, activation='softsign'),
    Dense(units=100, activation='softsign'),
    Dense(units=100, activation='softsign'),
    Dense(units=out_dim, activation = 'linear'),
    ])
    
    model.compile(loss='mse', optimizer='Adam', metrics=['mae'])
    model.fit(x=train_x,y=train_y,epochs=10000,validation_data=valid_set,batch_size=25,verbose=1)
    
    performance = model.evaluate(x=test_x,y=test_y)
    models.append(model)
    MAE.append(performance[1])

p = model.predict(np.array(test_x))

predicted_e = scaler.inverse_transform(p[:,0].reshape(-1,1))
#print(predicted_e)
predicted_g = scaler.inverse_transform(p[:,1].reshape(-1,1))
#print(predicted_g)
actual_e = scaler.inverse_transform(test_e)
print(np.hstack((predicted_e,actual_e)))
#
print("Mean absolute error of the actual energies: ", np.sum(np.absolute((predicted_e - actual_e))) / len(predicted_g))
print("Percent error of actual energies is: ", np.mean((predicted_e - actual_e) / actual_e))

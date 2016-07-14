#  _________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2014 Sandia Corporation.
#  Under the terms of Contract DE-AC04-94AL85000 with Sandia Corporation,
#  the U.S. Government retains certain rights in this software.
#  This software is distributed under the BSD License.
#  _________________________________________________________________________

# baa99: Annotated with location of stochastic rhs entries
#        for use with pysp2smps conversion tool.

import itertools

from pyomo.pysp.annotations import (PySP_ConstraintStageAnnotation,
                                    PySP_StochasticRHSAnnotation)

#
# Import the reference model
#
from baa99_basemodel import model

#
# Annotate the model to enable SMPS conversion
# of the explicit scenario tree defined later
# in this file
#

model.constraint_stage = PySP_ConstraintStageAnnotation()
model.constraint_stage.declare(model.s1, 2)
model.constraint_stage.declare(model.s2, 2)
model.constraint_stage.declare(model.d1, 2)
model.constraint_stage.declare(model.d2, 2)

model.stoch_rhs = PySP_StochasticRHSAnnotation()
model.stoch_rhs.declare(model.d1)
model.stoch_rhs.declare(model.d2)

#
# Define the scenario tree and provide a scenario instance
# creation callback
#
num_scenarios = len(model.d1_rhs_table) * len(model.d2_rhs_table)
scenario_data = dict(('Scenario'+str(i), (d1val, d2val))
                      for i, (d1val, d2val) in
                     enumerate(itertools.product(model.d1_rhs_table,
                                                 model.d2_rhs_table), 1))

def pysp_scenario_tree_model_callback():
    from pyomo.pysp.scenariotree.tree_structure_model import \
        CreateConcreteTwoStageScenarioTreeModel

    st_model = CreateConcreteTwoStageScenarioTreeModel(num_scenarios)

    first_stage = st_model.Stages.first()
    second_stage = st_model.Stages.last()

    # First Stage
    st_model.StageCost[first_stage] = 'FirstStageCost'
    st_model.StageVariables[first_stage].add('x1')
    st_model.StageVariables[first_stage].add('x2')

    # Second Stage
    st_model.StageCost[second_stage] = 'SecondStageCost'
    st_model.StageVariables[second_stage].add('v1')
    st_model.StageVariables[second_stage].add('v2')
    st_model.StageVariables[second_stage].add('u1')
    st_model.StageVariables[second_stage].add('u2')
    st_model.StageVariables[second_stage].add('w11')
    st_model.StageVariables[second_stage].add('w12')
    st_model.StageVariables[second_stage].add('w22')

    return st_model

def pysp_instance_creation_callback(scenario_name, node_names):

    #
    # Clone a new instance and update the stochastic
    # parameters from the sampled scenario
    #

    instance = model.clone()

    d1_rhs_val, d2_rhs_val = scenario_data[scenario_name]
    instance.d1_rhs.value = d1_rhs_val
    instance.d2_rhs.value = d2_rhs_val

    return instance

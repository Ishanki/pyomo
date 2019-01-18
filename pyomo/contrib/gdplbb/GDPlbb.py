import logging

from six import iteritems

import pyomo.util.plugin
from pyomo.core.base import expr as EXPR
from pyomo.core.base import (Block, Constraint, ConstraintList, Expression,
                             Objective, Set, Suffix, TransformationFactory,
                             Var, maximize, minimize, value)
from pyomo.core.base.block import generate_cuid_names
from pyomo.core.base.symbolic import differentiate
from pyomo.gdp import Disjunct, Disjunction
from pyomo.opt import TerminationCondition as tc
from pyomo.opt import SolutionStatus, SolverFactory, SolverStatus
from pyomo.opt.results import ProblemSense, SolverResults
from pyomo.common.config import (ConfigBlock, ConfigList, ConfigValue, In,
                                 NonNegativeFloat, NonNegativeInt,
                                 add_docstring_list)
from pyomo.common.modeling import unique_component_name

import heapq

@SolverFactory.register('gdplbb',
        doc='Branch and Bound based GDP Solver')
class GDPlbbSolver(object):
    """A branch and bound-based GDP solver."""
    CONFIG = ConfigBlock("gdplbb")
    def available(self, exception_flag=True):
        """Check if solver is available.

        TODO: For now, it is always available. However, sub-solvers may not
        always be available, and so this should reflect that possibility.

        """
        return True

    def solve(self, model, **kwds):
        """
        PSEUDOCODE
        Initialize minheap h ordered by objective value
        root = model.clone
        root.init_active_disj = list of currently active disjunctions
        root.curr_active_disj = []
        for each disj in root.init_active_disj
        	Deactivate disj
        Apply Sat Solver to root
        if infeasible
        	Return no-solution EXIT
        solve root
        push (root,root.obj.value()) onto minheap h

        while not heap.empty()
        	pop (m,v) from heap
        	if len(m.init_active_disj == 0):
        		copy m to model
        		return good-solution EXIT
        	find disj D in m.init_active_disj

        	for each disjunct d in D
        		set d false
        	for each disjunct d in D
        		set d true
        		mnew = m.clone
        		Apply Sat Solver to mnew
        		if mnew infeasible
        			Return no-solution EXIT
        		solve(mnew)
        		push (mnew,menw.obj.value()) onto minheap h
        		set d false
        """

        #Validate model to be used with gdplbb
        self.validate_model(model)
        #Set solver as an MINLP
        solver = SolverFactory('baron')

        #Initialize ist containing indicator vars for reupdating model after solving
        indicator_list_name = unique_component_name(model,"_indicator_list")
        indicator_vars = []
        for disjunction in model.component_data_objects(
            ctype = Disjunction, active=True):
            for disjunct in disjunction.disjuncts:
                indicator_vars.append(disjunct.indicator_var)
        setattr(model, indicator_list_name, indicator_vars)

        #clone original model for root node of branch and bound
        root = model.clone()
        #set up lists to keep track of which disjunctions have been covered.

        #this list keeps track of the original disjunctions that were active and are soon to be inactive
        init_active_disjunctions_name = unique_component_name(root,"_init_active_disjunctions")
        init_active_disjunctions = list(root.component_data_objects(
            ctype = Disjunction, active=True))
        setattr(root,init_active_disjunctions_name, init_active_disjunctions)

        #this list keeps track of the disjunctions that have been activated by the branch and bound
        curr_active_disjunctions_name = unique_component_name(root,"_curr_active_disjunctions")
        curr_active_disjunctions = []
        setattr(root,curr_active_disjunctions_name, curr_active_disjunctions)

        #deactivate all disjunctions in the model
        for djn in getattr(root,init_active_disjunctions_name):
            djn.deactivate()

        #Satisfiability check would go here

        #solve the root node
        obj_value = self.minlp_solve(root,solver)
        print obj_value


        #initialize minheap for Branch and Bound algorithm
        heap = []
        heapq.heappush(heap,(obj_value,root))

        while len(heap)>0:
            mdl = heapq.heappop(heap)[1]
            self.indicate(mdl)
            if(len(getattr(mdl,init_active_disjunctions_name)) ==  0):
                orig_var_list = getattr(model, indicator_list_name)
                best_soln_var_list = getattr(mdl, indicator_list_name)
                for orig_var, new_var in zip(orig_var_list,best_soln_var_list):
                    if not orig_var.is_fixed():
                        orig_var.value = new_var.value
                self.indicate(model)
                TransformationFactory('gdp.fix_disjuncts').apply_to(model)

                return solver.solve(model)

            disjunction = getattr(mdl,init_active_disjunctions_name).pop(0)
            for disj in list(disjunction.disjuncts):
                disj.indicator_var = 0
            disjunction.activate()
            getattr(mdl,curr_active_disjunctions_name).append(disjunction)
            for disj in list(disjunction.disjuncts):
                disj.indicator_var = 0
            for disj in list(disjunction.disjuncts):
                disj.indicator_var = 1
                mnew = mdl.clone()
                disj.indicator_var = 0
                obj_value = self.minlp_solve(mnew,solver)
                print obj_value
                #self.indicate(mnew)

                heapq.heappush(heap,(obj_value,mnew))



    def validate_model(self,model):
        #Validates that model has only exclusive disjunctions
        for d in model.component_data_objects(
            ctype = Disjunction, active=True):
            if(not d.xor):
                raise ValueError('GDPlbb unable to handle '
                                'non-exclusive disjunctions')
        objectives = model.component_data_objects(Objective, active=True)
        obj = next(objectives, None)
        if next(objectives, None) is not None:
            raise RuntimeError(
                "GDP LBB solver is unable to handle model with multiple active objectives.")
        if obj is None:
            raise RuntimeError(
                "GDP LBB solver is unable to handle model with no active objective.")

    def minlp_solve(self,gdp,solver):
        minlp = gdp.clone()
        TransformationFactory('gdp.fix_disjuncts').apply_to(minlp)
        for disjunct in minlp.component_data_objects(
            ctype = Disjunct, active=True):
            disjunct.deactivate() #TODO this is HACK
        result = solver.solve(minlp)
        if (result.solver.status is SolverStatus.ok and
                result.solver.termination_condition is tc.optimal):
                objectives = minlp.component_data_objects(Objective, active=True)
                obj = next(objectives, None)
                return value(obj.expr)
        else:
                return float('inf')
        delete(minlp)
    def __enter__(self):
        return self

    def __exit__(self, t, v, traceback):
        pass

    def indicate(self,model):
        for disjunction in model.component_data_objects(
            ctype = Disjunction, active=True):
            for disjunct in disjunction.disjuncts:
                print (disjunction.name,disjunct.name,value(disjunct.indicator_var))

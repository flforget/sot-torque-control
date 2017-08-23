# -*- coding: utf-8 -*-1
"""
2014, LAAS/CNRS
@author: Andrea Del Prete
"""

from dynamic_graph import plug
from dynamic_graph.sot.torque_control.force_torque_estimator import ForceTorqueEstimator
from dynamic_graph.sot.torque_control.numerical_difference import NumericalDifference as VelAccEstimator
from dynamic_graph.sot.torque_control.joint_torque_controller import JointTorqueController
from dynamic_graph.sot.torque_control.joint_trajectory_generator import JointTrajectoryGenerator
from dynamic_graph.sot.torque_control.nd_trajectory_generator import NdTrajectoryGenerator
from dynamic_graph.sot.torque_control.se3_trajectory_generator import SE3TrajectoryGenerator
from dynamic_graph.sot.torque_control.control_manager import ControlManager
from dynamic_graph.sot.torque_control.inverse_dynamics_controller import InverseDynamicsController
from dynamic_graph.sot.torque_control.admittance_controller import AdmittanceController
from dynamic_graph.sot.torque_control.position_controller import PositionController
from dynamic_graph.tracer_real_time import TracerRealTime
from dynamic_graph.sot.torque_control.hrp2.motors_parameters import NJ
from dynamic_graph.sot.torque_control.hrp2.motors_parameters import *
from dynamic_graph.sot.torque_control.hrp2.joint_pos_ctrl_gains import *

def create_encoders(robot):
    from dynamic_graph.sot.core import Selec_of_vector
    encoders = Selec_of_vector('qn')
    plug(robot.device.robotState,     encoders.sin);
    encoders.selec(6,NJ+6);
    return encoders

def create_base_estimator(robot, dt, urdf, conf):    
    from dynamic_graph.sot.torque_control.base_estimator import BaseEstimator
    base_estimator = BaseEstimator('base_estimator');
    plug(robot.encoders.sout,               base_estimator.joint_positions);
    plug(robot.device.forceRLEG,            base_estimator.forceRLEG);
    plug(robot.device.forceLLEG,            base_estimator.forceLLEG);
    plug(robot.estimator_kin.dx,            base_estimator.joint_velocities);
    plug(robot.imu_filter.imu_quat,         base_estimator.imu_quaternion);
    
    base_estimator.set_imu_weight(conf.w_imu);
    base_estimator.set_stiffness_right_foot(conf.K);
    base_estimator.set_stiffness_left_foot(conf.K);
    base_estimator.set_zmp_std_dev_right_foot(conf.std_dev_zmp)
    base_estimator.set_zmp_std_dev_left_foot(conf.std_dev_zmp)
    base_estimator.set_normal_force_std_dev_right_foot(conf.std_dev_fz)
    base_estimator.set_normal_force_std_dev_left_foot(conf.std_dev_fz)
    base_estimator.set_zmp_margin_right_foot(conf.zmp_margin)
    base_estimator.set_zmp_margin_left_foot(conf.zmp_margin)
    base_estimator.set_normal_force_margin_right_foot(conf.normal_force_margin)
    base_estimator.set_normal_force_margin_left_foot(conf.normal_force_margin)
    base_estimator.set_right_foot_sizes(conf.RIGHT_FOOT_SIZES)
    base_estimator.set_left_foot_sizes(conf.LEFT_FOOT_SIZES)
    
    base_estimator.init(dt, urdf);
    return base_estimator;
    
def create_imu_offset_compensation(robot, dt):
    from dynamic_graph.sot.torque_control.imu_offset_compensation import ImuOffsetCompensation
    imu_offset_compensation = ImuOffsetCompensation('imu_offset_comp');
    plug(robot.device.accelerometer, imu_offset_compensation.accelerometer_in);
    plug(robot.device.gyrometer,     imu_offset_compensation.gyrometer_in);
    imu_offset_compensation.init(dt);
    return imu_offset_compensation;

def create_imu_filter(ent, dt):
    from dynamic_graph.sot.torque_control.madgwickahrs import MadgwickAHRS
    imu_filter = MadgwickAHRS('imu_filter');
    imu_filter.init(dt);
    plug(ent.imu_offset_compensation.accelerometer_out, imu_filter.accelerometer);
    plug(ent.imu_offset_compensation.gyrometer_out,     imu_filter.gyroscope);
    return imu_filter;

def create_com_traj_gen(dt=0.001):
    com_traj_gen = NdTrajectoryGenerator("com_traj_gen");
    import dynamic_graph.sot.torque_control.hrp2.balance_ctrl_conf as conf
    com_traj_gen.initial_value.value = conf.COM_DES;
    com_traj_gen.init(dt,3);
    return com_traj_gen ;

def create_free_flyer_locator(ent, robot_name="robot"):
    from dynamic_graph.sot.torque_control.free_flyer_locator import FreeFlyerLocator
    ff_locator = FreeFlyerLocator("ffLocator");
    plug(ent.device.robotState,             ff_locator.base6d_encoders);
    plug(ent.estimator_kin.dx,              ff_locator.joint_velocities);
    try:
        plug(ff_locator.base6dFromFoot_encoders, ent.dynamic.position);
    except:
        print "[WARNING] Could not connect to dynamic entity, probably because you are in simulation"
        pass;
    ff_locator.init(robot_name);
    return ff_locator;
    
def create_flex_estimator(robot, dt=0.001):
    from dynamic_graph.sot.application.state_observation.initializations.hrp2_model_base_flex_estimator_imu_force import HRP2ModelBaseFlexEstimatorIMUForce
    flex_est = HRP2ModelBaseFlexEstimatorIMUForce(robot, useMocap=False, dt=dt);
    flex_est.setOn(False);
    flex_est.interface.setExternalContactPresence(False);
    flex_est.interface.enabledContacts_lf_rf_lh_rh.value=(1,1,0,0);
    plug(robot.ff_locator.v, flex_est.leftFootVelocity.sin2);
    plug(robot.ff_locator.v, flex_est.rightFootVelocity.sin2);
    plug(robot.ff_locator.v, flex_est.inputVel.sin2);
    plug(robot.ff_locator.v, flex_est.DCom.sin2);
    return flex_est;
    
def create_floatingBase(ent):
    from dynamic_graph.sot.application.state_observation.initializations.hrp2_model_base_flex_estimator_imu_force import FromLocalToGLobalFrame 
    floatingBase = FromLocalToGLobalFrame(ent.flex_est, "FloatingBase")
    plug(ent.ff_locator.freeflyer_aa, floatingBase.sinPos);

    from dynamic_graph.sot.core import Selec_of_vector
    base_vel_no_flex = Selec_of_vector('base_vel_no_flex');
    plug(ent.ff_locator.v, base_vel_no_flex.sin);
    base_vel_no_flex.selec(0, 6);
    plug(base_vel_no_flex.sout,   floatingBase.sinVel);
    return floatingBase
    
def create_position_controller(ent, dt=0.001, robot_name="robot"):
    posCtrl = PositionController('pos_ctrl')
    posCtrl.Kp.value = tuple(kp_pos);
    posCtrl.Kd.value = tuple(kd_pos);
    posCtrl.Ki.value = tuple(ki_pos);
    posCtrl.dqRef.value = NJ*(0.0,);
    plug(ent.device.robotState,             posCtrl.base6d_encoders);  
    try:  # this works only in simulation
        plug(ent.device.jointsVelocities,    posCtrl.jointsVelocities);
    except:
        plug(ent.estimator_kin.dx, posCtrl.jointsVelocities);
        pass;
#    plug(posCtrl.pwmDes,                ent.device.control);
    try:
        plug(ent.traj_gen.q,       posCtrl.qRef);
    except:
        pass;
    posCtrl.init(dt, robot_name);
    return posCtrl;

def create_trajectory_generator(device, dt=0.001, robot_name="robot"):
    jtg = JointTrajectoryGenerator("jtg");
    plug(device.robotState,             jtg.base6d_encoders);
    jtg.init(dt, robot_name);
    return jtg;

def create_estimators(ent, conf):
    estimator_kin = VelAccEstimator("estimator_kin");
    estimator_ft = ForceTorqueEstimator("estimator_ft");

    plug(ent.encoders.sout,                             estimator_kin.x);
    plug(ent.device.robotState,                         estimator_ft.base6d_encoders);
    plug(ent.imu_offset_compensation.accelerometer_out, estimator_ft.accelerometer);
    plug(ent.imu_offset_compensation.gyrometer_out,     estimator_ft.gyroscope);
    plug(ent.device.forceRLEG,                          estimator_ft.ftSensRightFoot);
    plug(ent.device.forceLLEG,                          estimator_ft.ftSensLeftFoot);
    plug(ent.device.forceRARM,                          estimator_ft.ftSensRightHand);
    plug(ent.device.forceLARM,                          estimator_ft.ftSensLeftHand);
    plug(ent.device.currents,                           estimator_ft.currentMeasure);

    plug(estimator_kin.x_filtered, estimator_ft.q_filtered);
    plug(estimator_kin.dx,         estimator_ft.dq_filtered);
    plug(estimator_kin.ddx,        estimator_ft.ddq_filtered);
    try:
        plug(ent.traj_gen.dq,       estimator_ft.dqRef);
        plug(ent.traj_gen.ddq,      estimator_ft.ddqRef);
    except:
        pass;
    estimator_ft.wCurrentTrust.value     = tuple(NJ*[conf.CURRENT_TORQUE_ESTIMATION_TRUST,])
    estimator_ft.saturationCurrent.value = tuple(NJ*[conf.SATURATION_CURRENT,])
    estimator_ft.motorParameterKt_p.value  = tuple(Kt_p)
    estimator_ft.motorParameterKt_n.value  = tuple(Kt_n)
    estimator_ft.motorParameterKf_p.value  = tuple(Kf_p)
    estimator_ft.motorParameterKf_n.value  = tuple(Kf_n)
    estimator_ft.motorParameterKv_p.value  = tuple(Kv_p)
    estimator_ft.motorParameterKv_n.value  = tuple(Kv_n)
    estimator_ft.motorParameterKa_p.value  = tuple(Ka_p)
    estimator_ft.motorParameterKa_n.value  = tuple(Ka_n)

    delay = conf.ESTIMATOR_DELAY;
    estimator_ft.init(conf.dt, delay,delay,delay,delay,True);
    estimator_kin.init(conf.dt, NJ, delay);
    
    return (estimator_ft, estimator_kin);
        
def create_torque_controller(ent, dt=0.001, robot_name="robot"):
    torque_ctrl = JointTorqueController("jtc");
    plug(ent.device.robotState,             torque_ctrl.base6d_encoders);
    plug(ent.estimator_kin.dx,    torque_ctrl.jointsVelocities);
    plug(ent.estimator_kin.ddx, torque_ctrl.jointsAccelerations);
    plug(ent.estimator_ft.jointsTorques,       torque_ctrl.jointsTorques);
    plug(ent.estimator_ft.currentFiltered,      torque_ctrl.measuredCurrent);
    torque_ctrl.jointsTorquesDesired.value = NJ*(0.0,);
    torque_ctrl.KpTorque.value = tuple(k_p_torque);
    torque_ctrl.KiTorque.value = NJ*(0.0,);
    torque_ctrl.KpCurrent.value = tuple(k_p_current);
    torque_ctrl.KiCurrent.value = NJ*(0.0,);
    torque_ctrl.k_tau.value = tuple(k_tau);
    torque_ctrl.k_v.value   = tuple(k_v);
    torque_ctrl.frictionCompensationPercentage.value = NJ*(FRICTION_COMPENSATION_PERCENTAGE,);

    torque_ctrl.motorParameterKt_p.value  = tuple(Kt_p)
    torque_ctrl.motorParameterKt_n.value  = tuple(Kt_n)
    torque_ctrl.motorParameterKf_p.value  = tuple(Kf_p)
    torque_ctrl.motorParameterKf_n.value  = tuple(Kf_n)
    torque_ctrl.motorParameterKv_p.value  = tuple(Kv_p)
    torque_ctrl.motorParameterKv_n.value  = tuple(Kv_n)
    torque_ctrl.motorParameterKa_p.value  = tuple(Ka_p)
    torque_ctrl.motorParameterKa_n.value  = tuple(Ka_n)
    torque_ctrl.polySignDq.value          = NJ*(3,); 
    torque_ctrl.init(dt, robot_name);
    return torque_ctrl;
   
def create_balance_controller(ent, conf):
    ctrl = InverseDynamicsBalanceController("invDynBalCtrl");

    try:
        plug(ent.ff_locator.base6dFromFoot_encoders, ctrl.q);
        plug(ent.ff_locator.v, ctrl.v);
    except:
        plug(ent.base_estimator.q, ctrl.q);
        plug(ent.base_estimator.v, ctrl.v);

    plug(ent.estimator_ft.contactWrenchRightSole,  ctrl.wrench_right_foot);
    plug(ent.estimator_ft.contactWrenchLeftSole,   ctrl.wrench_left_foot);
    try:
        plug(ctrl.tau_des,                          ent.torque_ctrl.jointsTorquesDesired);
    except:
        print "[WARNING] Could not connect to torque_ctrl entity. Probably that is because you are in simulation.";
            
    plug(ctrl.tau_des,                          ent.estimator_ft.tauDes);

    plug(ctrl.right_foot_pos,       ent.rf_traj_gen.initial_value);
    plug(ent.rf_traj_gen.x,         ctrl.rf_ref_pos);
    plug(ent.rf_traj_gen.dx,        ctrl.rf_ref_vel);
    plug(ent.rf_traj_gen.ddx,       ctrl.rf_ref_acc);

    plug(ctrl.left_foot_pos,        ent.lf_traj_gen.initial_value);
    plug(ent.lf_traj_gen.x,         ctrl.lf_ref_pos);
    plug(ent.lf_traj_gen.dx,        ctrl.lf_ref_vel);
    plug(ent.lf_traj_gen.ddx,       ctrl.lf_ref_acc);
    
    plug(ent.traj_gen.q,                        ctrl.posture_ref_pos);
    plug(ent.traj_gen.dq,                       ctrl.posture_ref_vel);
    plug(ent.traj_gen.ddq,                      ctrl.posture_ref_acc);
    plug(ent.com_traj_gen.x,                    ctrl.com_ref_pos);
    plug(ent.com_traj_gen.dx,                   ctrl.com_ref_vel);
    plug(ent.com_traj_gen.ddx,                  ctrl.com_ref_acc);

    ctrl.rotor_inertias.value = conf.ROTOR_INERTIAS;
    ctrl.gear_ratios.value = conf.GEAR_RATIOS;
    ctrl.contact_normal.value = conf.FOOT_CONTACT_NORMAL;
    ctrl.contact_points.value = conf.RIGHT_FOOT_CONTACT_POINTS;
    ctrl.f_min.value = conf.fMin;
    ctrl.f_max.value = conf.fMax;
#    ctrl.f_max_right_foot.value = conf.fMax;
    ctrl.mu.value = conf.mu[0];
    ctrl.weight_contact_forces.value = (1e2, 1e2, 1e0, 1e3, 1e3, 1e3);
    ctrl.kp_com.value = 3*(conf.kp_com,);
    ctrl.kd_com.value = 3*(conf.kd_com,);
    ctrl.kp_constraints.value = 6*(conf.kp_constr,);
    ctrl.kd_constraints.value = 6*(conf.kd_constr,);
    ctrl.kp_feet.value = 6*(conf.kp_feet,);
    ctrl.kd_feet.value = 6*(conf.kd_feet,);
    ctrl.kp_posture.value = NJ*(conf.kp_posture,);
    ctrl.kd_posture.value = NJ*(conf.kd_posture,);
    ctrl.kp_pos.value = NJ*(conf.kp_pos,);
    ctrl.kd_pos.value = NJ*(conf.kd_pos,);

    ctrl.w_com.value = conf.w_com;
    ctrl.w_feet.value = conf.w_feet;
    ctrl.w_forces.value = conf.w_forces;
    ctrl.w_posture.value = conf.w_posture;
    ctrl.w_base_orientation.value = conf.w_base_orientation;
    ctrl.w_torques.value = conf.w_torques;
    
    ctrl.init(conf.dt, conf.urdfFileName, conf.robot_name);
    
    return ctrl;
    
def create_inverse_dynamics(ent, dt=0.001):
    inv_dyn_ctrl = InverseDynamicsController("inv_dyn");
    plug(ent.device.robotState,             inv_dyn_ctrl.base6d_encoders);
    plug(ent.estimator_kin.dx,              inv_dyn_ctrl.jointsVelocities);
    plug(ent.traj_gen.q,                    inv_dyn_ctrl.qRef);
    plug(ent.traj_gen.dq,                   inv_dyn_ctrl.dqRef);
    plug(ent.traj_gen.ddq,                  inv_dyn_ctrl.ddqRef);
    plug(ent.estimator_ft.contactWrenchRightSole,   inv_dyn_ctrl.fRightFoot);
    plug(ent.estimator_ft.contactWrenchLeftSole,    inv_dyn_ctrl.fLeftFoot);
    plug(ent.estimator_ft.contactWrenchRightHand,   inv_dyn_ctrl.fRightHand);
    plug(ent.estimator_ft.contactWrenchLeftHand,    inv_dyn_ctrl.fLeftHand);
    plug(ent.traj_gen.fRightFoot,           inv_dyn_ctrl.fRightFootRef);
    plug(ent.traj_gen.fLeftFoot,            inv_dyn_ctrl.fLeftFootRef);
    plug(ent.traj_gen.fRightHand,           inv_dyn_ctrl.fRightHandRef);
    plug(ent.traj_gen.fLeftHand,            inv_dyn_ctrl.fLeftHandRef);
    plug(ent.estimator_ft.baseAngularVelocity, inv_dyn_ctrl.baseAngularVelocity);
    plug(ent.estimator_ft.baseAcceleration,    inv_dyn_ctrl.baseAcceleration);
    plug(inv_dyn_ctrl.tauDes,           ent.torque_ctrl.jointsTorquesDesired);
    plug(inv_dyn_ctrl.tauFF,            ent.torque_ctrl.tauFF);
    plug(inv_dyn_ctrl.tauFB,            ent.torque_ctrl.tauFB);
    plug(inv_dyn_ctrl.tauDes,           ent.estimator_ft.tauDes);
    plug(ent.estimator_ft.dynamicsError,       inv_dyn_ctrl.dynamicsError);
    
    inv_dyn_ctrl.dynamicsErrorGain.value = (NJ+6)*(0.0,);
    inv_dyn_ctrl.Kp.value = tuple(k_s); # joint proportional gains
    inv_dyn_ctrl.Kd.value = tuple(k_d); # joint derivative gains
    inv_dyn_ctrl.Kf.value = tuple(k_f); # force proportional gains
    inv_dyn_ctrl.Ki.value = tuple(k_i); # force integral gains
    inv_dyn_ctrl.controlledJoints.value = NJ*(1.0,);
    inv_dyn_ctrl.init(dt);
    return inv_dyn_ctrl;
        
def create_ctrl_manager(ent, conf):
    ctrl_manager = ControlManager("ctrl_man");        

#    plug(ent.torque_ctrl.predictedJointsTorques, ctrl_manager.tau_predicted);
    ctrl_manager.tau_predicted.value = NJ*(0.0,);
#    plug(ent.estimator_ft.jointsTorques,            ctrl_manager.tau);
    ctrl_manager.max_tau.value = NJ*(conf.CTRL_MANAGER_TAU_MAX,);
    ctrl_manager.max_current.value = NJ*(conf.CTRL_MANAGER_CURRENT_MAX,);
    ctrl_manager.percentageDriverDeadZoneCompensation.value = NJ*(conf.PERCENTAGE_DRIVER_DEAD_ZONE_COMPENSATION,);
    ctrl_manager.signWindowsFilterSize.value = NJ*(conf.SIGN_WINDOW_FILTER_SIZE,);
    ctrl_manager.bemfFactor.value = NJ*(0.0,);
    #ctrl_manager.bemfFactor.value = tuple(Kpwm*0.1);
#    plug(ent.device.robotState,                  ctrl_manager.base6d_encoders);
#    plug(ctrl_manager.pwmDesSafe,       ent.device.control);
    
    # Init should be called before addCtrlMode 
    # because the size of state vector must be known.
    ctrl_manager.init(conf.dt, conf.urdfFileName, conf.CTRL_MANAGER_CURRENT_TO_CONTROL_GAIN,
                      conf.CTRL_MANAGER_CURRENT_MAX, conf.robot_name)

    # Set the map from joint name to joint ID
    for key in conf.mapJointNameToID:
      ctrl_manager.setNameToId(key,conf.mapJointNameToID[key])
            
    # Set the map joint limits for each id
    for key in conf.mapJointLimits:
      ctrl_manager.setJointLimitsFromId(key,conf.mapJointLimits[key][0], \
                              conf.mapJointLimits[key][1])
          
    # Set the force limits for each id
    for key in conf.mapForceIdToForceLimits:
      ctrl_manager.setForceLimitsFromId(key,tuple(conf.mapForceIdToForceLimits[key][0]), \
                              tuple(conf.mapForceIdToForceLimits[key][1]))

    # Set the force sensor id for each sensor name
    for key in conf.mapNameToForceId:
      ctrl_manager.setForceNameToForceId(key,conf.mapNameToForceId[key])

    # Set the map from the urdf joint list to the sot joint list
    ctrl_manager.setJointsUrdfToSot(conf.urdftosot)

    # Set the foot frame name
    for key in conf.footFrameNames:
      ctrl_manager.setFootFrameName(key,conf.footFrameNames[key])

    ctrl_manager.setRightFootSoleXYZ(conf.rightFootSensorXYZ)
    ctrl_manager.setDefaultMaxCurrent(conf.CTRL_MANAGER_CURRENT_MAX)
    
#    plug(ctrl_manager.pwmDes,           ent.torque_ctrl.pwm);
#    ctrl_manager.addCtrlMode("pos");
#    ctrl_manager.addCtrlMode("torque");    
#    plug(ent.estimator_kin.dx,    ctrl_manager.dq);
#    plug(ent.torque_ctrl.controlCurrent,    ctrl_manager.ctrl_torque);
#    plug(ent.pos_ctrl.pwmDes,               ctrl_manager.ctrl_pos);
#    plug(ctrl_manager.joints_ctrl_mode_torque,  ent.inv_dyn.active_joints);
#    ctrl_manager.setCtrlMode("all", "pos");
    
    return ctrl_manager;

def create_admittance_ctrl(ent, dt=0.001):
    admit_ctrl = AdmittanceController("adm_ctrl");
    plug(ent.device.robotState,             admit_ctrl.base6d_encoders);
    plug(ent.estimator_kin.dx,    admit_ctrl.jointsVelocities);
    plug(ent.estimator_ft.contactWrenchRightSole,   admit_ctrl.fRightFoot);
    plug(ent.estimator_ft.contactWrenchLeftSole,    admit_ctrl.fLeftFoot);
    plug(ent.estimator_ft.contactWrenchRightHand,   admit_ctrl.fRightHand);
    plug(ent.estimator_ft.contactWrenchLeftHand,    admit_ctrl.fLeftHand);
    plug(ent.traj_gen.fRightFoot,           admit_ctrl.fRightFootRef);
    plug(ent.traj_gen.fLeftFoot,            admit_ctrl.fLeftFootRef);
    plug(ent.traj_gen.fRightHand,           admit_ctrl.fRightHandRef);
    plug(ent.traj_gen.fLeftHand,            admit_ctrl.fLeftHandRef);
    
    admit_ctrl.damping.value = 4*(0.05,);
    admit_ctrl.Kd.value = NJ*(0,);
    kf = -0.0005;
    km = -0.008;
    admit_ctrl.Kf.value = 3*(kf,)+3*(km,)+3*(kf,)+3*(km,)+3*(kf,)+3*(km,)+3*(kf,)+3*(km,);
    
    ent.ctrl_manager.addCtrlMode("adm");
    plug(admit_ctrl.qDes,                       ent.ctrl_manager.ctrl_adm);
    plug(ent.ctrl_manager.joints_ctrl_mode_adm, admit_ctrl.controlledJoints);
    
    admit_ctrl.init(dt);
    return admit_ctrl;

def create_topic(ros_import, signal, name, data_type='vector', sleep_time=0.1):
    ros_import.add(data_type, name+'_ros', name);
    plug(signal, ros_import.signal(name+'_ros'));
    from time import sleep
    sleep(sleep_time);
    

def create_ros_topics(ent):
    from dynamic_graph.ros import RosPublish
    ros = RosPublish('rosPublish');
    try:
        create_topic(ros, ent.device.robotState,      'robotState');
        create_topic(ros, ent.device.gyrometer,       'gyrometer');
        create_topic(ros, ent.device.accelerometer,   'accelerometer');
        create_topic(ros, ent.device.forceRLEG,       'forceRLEG');
        create_topic(ros, ent.device.forceLLEG,       'forceLLEG');
        create_topic(ros, ent.device.currents,        'currents');
#        create_topic(ros, ent.device.forceRARM,       'forceRARM');
#        create_topic(ros, ent.device.forceLARM,       'forceLARM');
        ent.device.after.addDownsampledSignal('rosPublish.trigger',1);
    except:
        pass;
    
    try:
        create_topic(ros, ent.estimator_kin.dx,               'jointsVelocities');
        create_topic(ros, ent.estimator_ft.contactWrenchLeftSole,          'contactWrenchLeftSole');
        create_topic(ros, ent.estimator_ft.contactWrenchRightSole,         'contactWrenchRightSole');
        create_topic(ros, ent.estimator_ft.jointsTorques,                  'jointsTorques');
#        create_topic(ros, ent.estimator.jointsTorquesFromInertiaModel,  'jointsTorquesFromInertiaModel');
#        create_topic(ros, ent.estimator.jointsTorquesFromMotorModel,    'jointsTorquesFromMotorModel');
#        create_topic(ros, ent.estimator.currentFiltered,                'currentFiltered');
    except:
        pass;

    try:
        create_topic(ros, ent.torque_ctrl.controlCurrent, 'controlCurrent');
        create_topic(ros, ent.torque_ctrl.desiredCurrent, 'desiredCurrent');
    except:
        pass;

    try:
        create_topic(ros, ent.traj_gen.q,   'q_ref');
#        create_topic(ros, ent.traj_gen.dq,  'dq_ref');
#        create_topic(ros, ent.traj_gen.ddq, 'ddq_ref');
    except:
        pass;

    try:
        create_topic(ros, ent.ctrl_manager.pwmDes,                  'i_des');
        create_topic(ros, ent.ctrl_manager.pwmDesSafe,              'i_des_safe');
#        create_topic(ros, ent.ctrl_manager.signOfControlFiltered,   'signOfControlFiltered');
#        create_topic(ros, ent.ctrl_manager.signOfControl,           'signOfControl');
    except:
        pass;

    try:
        create_topic(ros, ent.inv_dyn.tau_des, 'tau_des');
    except:
        pass;

    try:
        create_topic(ros, ent.ff_locator.base6dFromFoot_encoders,        'base6dFromFoot_encoders');
    except:
        pass;

    try:
        create_topic(ros, ent.floatingBase.soutPos, 'floatingBase_pos');
    except:
        pass;
    
    return ros;
    
    
def addTrace(tracer, entity, signalName):
    """
    Add a signal to a tracer
    """
    signal = '{0}.{1}'.format(entity.name, signalName);
    filename = '{0}-{1}'.format(entity.name, signalName);
    tracer.add(signal, filename);
    
def addSignalsToTracer(tracer, device):
    addTrace(tracer,device,'robotState');
    addTrace(tracer,device,'gyrometer');
    addTrace(tracer,device,'accelerometer');
    addTrace(tracer,device,'forceRLEG');
    addTrace(tracer,device,'forceLLEG');
    addTrace(tracer,device,'forceRARM');
    addTrace(tracer,device,'forceLARM');
    addTrace(tracer,device,'control');
    addTrace(tracer,device,'currents');


def create_tracer(device, traj_gen=None, estimator_ft=None, estimator_kin=None,
                  inv_dyn=None, torque_ctrl=None):
    tracer = TracerRealTime('motor_id_trace');
    tracer.setBufferSize(80*(2**20));
    tracer.open('/tmp/','dg_','.dat');
    device.after.addSignal('{0}.triger'.format(tracer.name));

    addSignalsToTracer(tracer, device);
        
    with open('/tmp/dg_info.dat', 'a') as f:
        if(estimator_ft!=None):
            f.write('Estimator F/T sensors delay: {0}\n'.format(ent.estimator_ft.getDelayFTsens()));
            f.write('Estimator use reference velocities: {0}\n'.format(ent.estimator_ft.getUseRefJointVel()));
            f.write('Estimator use reference accelerations: {0}\n'.format(ent.estimator_ft.getUseRefJointAcc()));
            f.write('Estimator accelerometer delay: {0}\n'.format(ent.estimator_ft.getDelayAcc()));
            f.write('Estimator gyroscope delay: {0}\n'.format(ent.estimator_ft.getDelayGyro()));
            f.write('Estimator use raw encoders: {0}\n'.format(ent.estimator_ft.getUseRawEncoders()));
            f.write('Estimator use f/t sensors: {0}\n'.format(ent.estimator_ft.getUseFTsensors()));
            f.write('Estimator f/t sensor offsets: {0}\n'.format(ent.estimator_ft.getFTsensorOffsets()));
        if(estimator_kin!=None):
            f.write('Estimator encoder delay: {0}\n'.format(ent.estimator_kin.getDelay()));
        if(inv_dyn!=None):
            f.write('Inv dyn Ks: {0}\n'.format(inv_dyn.Kp.value));
            f.write('Inv dyn Kd: {0}\n'.format(inv_dyn.Kd.value));
            f.write('Inv dyn Kf: {0}\n'.format(inv_dyn.Kf.value));
            f.write('Inv dyn Ki: {0}\n'.format(inv_dyn.Ki.value));
        if(torque_ctrl!=None):
            f.write('Torque ctrl KpTorque: {0}\n'.format (ent.torque_ctrl.KpTorque.value ));
            f.write('Torque ctrl KpCurrent: {0}\n'.format(ent.torque_ctrl.KpCurrent.value));
            f.write('Torque ctrl K_tau: {0}\n'.format(ent.torque_ctrl.k_tau.value));
            f.write('Torque ctrl K_v: {0}\n'.format(ent.torque_ctrl.k_v.value));
    f.close();
    return tracer;

def reset_tracer(device,tracer):
    from time import sleep
    tracer.stop();
    sleep(0.2);
    tracer.dump();
    sleep(0.2);
    tracer.close();
    sleep(0.2);
    tracer.clear();
    sleep(0.2);
    tracer = create_tracer(device);
    return tracer;

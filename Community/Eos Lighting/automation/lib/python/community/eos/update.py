"""
Eos Lighting

Process Light and Group updates
"""

from community.eos import log, config
from community.eos.util import *
from community.eos.constants import *

from core.log import log_traceback
from core.metadata import get_value, get_metadata
from core.utils import sendCommandCheckFirst, validate_item



@log_traceback
def update_scene(item):
    """
    Updates all lights and subgroups
    """
    for light_item in get_light_items(get_item_eos_group(item)):
        try: update_light(light_item)
        except: continue
    for group_item in get_group_items(get_item_eos_group(item)):
        update_group(group_item, True)


@log_traceback
def update_light(item):
    """
    Sends commands to lights based on scene.

    If light does not have metadata for the scene no command will be sent,
    except for the default scenes ``on`` and ``off``. The default values for
    built-in scenes can be customized in ``configuration.py`` if desired.
    """
    if get_value(item.name, META_NAME_EOS).lower() in ["false", "disabled"]:
        log.debug("Skipping update for light '{name}' as it is disabled".format(name=item.name))
        return
    else:
        log.debug("Processing update for light '{name}'".format(name=item.name))

    scene = get_scene_for_item(item)
    log.debug("Got scene '{scene}' for item '{name}'".format(scene=scene, name=item.name))

    if scene != SCENE_MANUAL:
        newState = get_state_for_scene(item, scene)
        if sendCommandCheckFirst(item.name, newState, floatPrecision=3):
            log.debug("Sent command '{command}' to light '{name}'".format(command=newState, name=item.name))
        else:
            log.debug("No command sent to light '{name}'".format(command=newState, name=item.name))
    else:
        log.debug("Scene for item '{name}' is '{scene}', no action taken".format(name=item.name, scene=scene))


@log_traceback
def update_group(target, only_if_scene_parent=False):
    if only_if_scene_parent and str(get_scene_item(target).state).lower() != SCENE_PARENT:
        return
    for light_item in get_light_items(target):
        try: update_light(light_item)
        except: continue
    for group_item in get_group_items(target):
        update_group(group_item, only_if_scene_parent)


def get_state_for_scene(item, scene):
    """Returns state for scene from ``item`` metadata.

    If ``item`` does not have a definition for ``scene`` and ``scene`` is ``on``
    or ``off`` it will look for look for a default state in configuration, if
    one is not found the built-in default state will be used.

    See full documentation for scene definitions here.
    """
    def constrain(value, min, max): return max if value > max else min if value < min else value

    def get_setting(key, depth=4):
        # gets a setting value by searching:
        # item-scene > item-default > type-scene-default > type-default
        if depth > 0 and scene in metadata and key in metadata.get(scene):
            value = metadata.get(scene, {}).get(key, None)
            if value is not None:
                log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}' from scene in item".format(
                    value=str(value), key=key, scene=scene, name=item.name))
                return value
            del value
        elif depth > 1 and key in metadata:
            value = metadata.get(key, None)
            if value is not None:
                log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}' from item defaults".format(
                    value=str(value), key=key, scene=scene, name=item.name))
                return value
            del value
        elif depth > 2 and light_type in config.scene_defaults and scene in config.scene_defaults.get(light_type).get(scene) and key in config.scene_defaults.get(light_type).get(scene):
            value = config.scene_defaults.get(light_type, {}).get(scene, {}).get(key, None)
            if value is not None:
                log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}' from scene defaults for '{type}'".format(
                    value=str(value), key=key, scene=scene, name=item.name, type=light_type))
                return value
            del value
        elif depth > 3 and light_type in config.scene_defaults and key in config.scene_defaults.get(light_type):
            value = config.scene_defaults.get(light_type, {}).get(key, None)
            if value is not None:
                log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}' from defaults for '{type}'".format(
                    value=str(value), key=key, scene=scene, name=item.name, type=light_type))
                return value
            del value
        else:
            log.debug("No value found for key '{key}' for scene '{scene}' for item '{name}' at depth {depth}".format(
                key=key, scene=scene, name=item.name, depth=depth))
            return None

    def get_scene_type():
        # gets the scene type
        for depth in range(1, 5):
            if get_setting(META_KEY_STATE, depth=depth) is not None:
                return SCENE_TYPE_FIXED
            elif get_setting(META_KEY_LEVEL_HIGH, depth=depth) is not None \
              or get_setting(META_KEY_LEVEL_LOW, depth=depth) is not None \
              or get_setting(META_KEY_STATE_HIGH, depth=depth) is not None \
              or get_setting(META_KEY_STATE_LOW, depth=depth) is not None:
                return SCENE_TYPE_SCALED
            elif get_setting(META_KEY_LEVEL_THRESHOLD, depth=depth) is not None:
                return SCENE_TYPE_THRESHOLD
        return None

    metadata = get_metadata(item.name, META_NAME_EOS).configuration
    log.debug("Got metadata dict for '{name}': {metadata}".format(name=item.name, metadata=metadata))

    light_type = LIGHT_TYPE_MAP.get(item.type.lower(), None)
    if light_type is None:
        log.error("Couldn't get light type for '{name}'".format(name=item.name))
        return str(item.state)
    else:
        log.debug("Got light type '{type}' for '{name}'".format(type=light_type, name=item.name))

    scene_type = get_scene_type()
    if scene_type is None:
        log.error("Couldn't get scene type for '{name}'".format(name=item.name))
        return str(item.state)
    else:
        log.debug("Got scene type '{type}' for '{name}'".format(type=scene_type, name=item.name))

    # Fixed State type
    if scene_type == SCENE_TYPE_FIXED:
        state = get_setting(META_KEY_STATE)
        log.debug("Got fixed state '{state}' for '{name}' scene '{scene}'".format(state=state, name=item.name, scene=scene))

    # Threshold type
    elif scene_type == SCENE_TYPE_THRESHOLD:
        if not get_setting(META_KEY_LEVEL_SOURCE):
            log.error("Threshold type scene requires '{level_source}' entry in '{eos}' namespace, nothing found for '{name}'".format(
                level_source=META_KEY_LEVEL_SOURCE, eos=META_NAME_EOS, name=item.name))
            return str(item.state)
        level_value = resolve_type(validate_item(get_setting(META_KEY_LEVEL_SOURCE)).state)
        if isinstance(level_value, str) and level_value.lower() in ["null", "undef"]:
            log.warn("Level item '{level_source}' for scene '{scene}' for item '{name}' has no value".format(
                level_source=get_setting(META_KEY_LEVEL_SOURCE), scene=scene, name=item.name))
            return str(item.state)
        log.debug("Got value '{value}' for level for scene '{scene}' for item '{name}'".format(value=level_value, scene=scene, name=item.name))

        level_threshold = get_setting(META_KEY_LEVEL_THRESHOLD)
        if level_threshold is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_LEVEL_THRESHOLD, scene=scene))
            return str(item.state)

        state_above = get_setting(META_KEY_STATE_ABOVE)
        if state_above is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_STATE_ABOVE, scene=scene))
            return str(item.state)

        state_below = get_setting(META_KEY_STATE_BELOW)
        if state_below is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_STATE_BELOW, scene=scene))
            return str(item.state)

        state = state_above if level_value > level_threshold else state_below
        log.debug("Calculated threshold state '{state}' for '{name}' scene '{scene}'".format(state=state, name=item.name, scene=scene))

    # Scaling type
    elif scene_type == SCENE_TYPE_SCALED and light_type in [LIGHT_TYPE_DIMMER, LIGHT_TYPE_COLOR]:
        if not get_setting(META_KEY_LEVEL_SOURCE):
            log.error("Scaling type scenes require a '{level_source}' entry in '{eos}' namespace, nothing found for '{name}'".format(
                level_source=META_KEY_LEVEL_SOURCE, eos=META_NAME_EOS, name=item.name))
            return str(item.state)
        level_value = resolve_type(validate_item(get_setting(META_KEY_LEVEL_SOURCE)).state)
        if isinstance(level_value, str) and level_value.lower() in ["null", "undef"]:
            log.warn("Level item '{level_source}' for scene '{scene}' for item '{name}' has no value".format(
                level_source=get_setting(META_KEY_LEVEL_SOURCE), scene=scene, name=item.name))
            return str(item.state)
        level_value = float(level_value)
        log.debug("Got value '{value}' for level for scene '{scene}' for item '{name}'".format(value=level_value, scene=scene, name=item.name))

        level_high = get_setting(META_KEY_LEVEL_HIGH)
        if level_high is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_LEVEL_HIGH, scene=scene))
            return str(item.state)
        level_high = float(level_high)

        level_low = get_setting(META_KEY_LEVEL_LOW)
        if level_low is None:
            level_low = 0.0
            log.debug("No value for key '{key}' for scene '{scene}' for item '{name}', using default '{value}'".format(
                key=META_KEY_LEVEL_LOW, scene=scene, name=item.name, value=level_low))
        level_low = float(level_low)

        state_high = get_setting(META_KEY_STATE_HIGH)
        if state_high is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_STATE_HIGH, scene=scene))
            return str(item.state)

        state_low = get_setting(META_KEY_STATE_LOW)
        if state_low is None:
            log.warn("Light '{name}' has no '{key}' for scene '{scene}' and there is no default to fall back to".format(name=item.name, key=META_KEY_STATE_LOW, scene=scene))
            return str(item.state)

        state_above = get_setting(META_KEY_STATE_ABOVE) or state_high
        log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}'".format(value=state_above, key=META_KEY_STATE_ABOVE, scene=scene, name=item.name))

        state_below = get_setting(META_KEY_STATE_BELOW) or state_low
        log.debug("Got value '{value}' for key '{key}' for scene '{scene}' for item '{name}'".format(value=state_below, key=META_KEY_STATE_BELOW, scene=scene, name=item.name))

        if level_value > level_high:
            state = state_above
        elif level_value <= level_low:
            state = state_below
        else:
            scaling_factor = (level_value - level_low) / (level_high - level_low)
            def scale(low, high): return int(round(low + (high - low) * scaling_factor))
            if isinstance(state_high, (int, float)): # Dimmer value
                state = scale(state_low, state_high)
            elif isinstance(state_high, list): # HSV list
                state = [scale(float(state_low[0]), float(state_high[0]))]
                state.append(scale(float(state_low[1]), float(state_high[1])))
                state.append(scale(float(state_low[2]), float(state_high[2])))

        log.debug("Calculated scaled state '{state}' for '{name}' scene '{scene}'".format(state=state, name=item.name, scene=scene))
    else:
        log.error("Invalid scene configuration for '{name}' scene '{scene}'".format(name=item.name, scene=scene))
        return str(item.state)

    if light_type == LIGHT_TYPE_SWITCH and isinstance(state, (str)) and state.upper() in ["ON", "OFF"]:
        state = state.upper()
    elif light_type == LIGHT_TYPE_DIMMER and isinstance(state, (int, float)):
        state = str(constrain(int(round(state)), 0, 100))
    elif light_type == LIGHT_TYPE_COLOR and isinstance(state, (int, float, list)):
        if isinstance(state, (int, float)):
            oldState = str("0,0,0" if isinstance(item.state, typesUnDef) else item.state).split(",")
            state = ",".join([str(oldState[0]), str(oldState[1]), str(constrain(int(round(state)), 0, 100))])
        else:
            if state[0] > 359: state[0] -= 359
            elif state[0] < 0: state[0] += 359
            constrain(state[1], 0, 100)
            constrain(state[2], 0, 100)
            state = ",".join([str(i) for i in state])
    else:
        log.warn("New state '{state}' for '{name}' scene '{scene}' is not valid for item type '{type}'".format(
            state=state, name=item.name, scene=scene, type=item.type))
        return str(item.state)

    log.debug("New state '{state}' for '{name}' scene '{scene}'".format(state=state, name=item.name, scene=scene))
    return state
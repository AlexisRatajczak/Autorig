import maya.cmds as cmds
import maya.mel as mel

def create_shelve_facial_rig():
    shelf_name = "Facial_Rig"

    top_shelf = mel.eval('$tmpVar=$gShelfTopLevel')

    if not cmds.shelfLayout(shelf_name, exists=True):
        cmds.shelfLayout(shelf_name, parent=top_shelf)
        print(f"Shelf '{shelf_name}' créée.")
    else:
        print(f"Shelf '{shelf_name}' existe déjà.")

    # Nettoyage
    for child in cmds.shelfLayout(shelf_name, q=True, childArray=True) or []:
        cmds.deleteUI(child)

    # -------------------------------------------------------------------------------------------------
    # ----------------------------------------- BUTTON BCS --------------------------------------------
    # -------------------------------------------------------------------------------------------------

    btn = cmds.shelfButton(
        parent=shelf_name,
        label="BCS_button",    
        imageOverlayLabel="BCS",
        annotation="DPK BCS UI",
        image1="tools_icon.png",
        sourceType="mel",
        command="DPK_bcsUI;"
    )

    popup = cmds.popupMenu(parent=btn)

    cmds.menuItem(
        label="Mirror Geo",
        sourceType="mel",
        command="DPK_mirrorGeoUI;"
    )

    cmds.menuItem(
        label="Paint Deform",
        sourceType="mel",
        command="DPK_paintDeform;"
    )

    cmds.menuItem(
        label="Rotate Delta",
        sourceType="mel",
        command="DPK_rotateDeltasUI;"
    )

    cmds.menuItem(
        label="Toggle View Setup",
        sourceType="mel",
        command="DPK_toggleViewSetup;"
    )
    # -------------------------------------------------------------------------------------------------
    # ------------------------------------------ SEPARATOR --------------------------------------------
    # -------------------------------------------------------------------------------------------------
    cmds.separator(
        parent=shelf_name,
        enable=1,
        width=12,
        height=35,
        manage=1,
        visible=1,
        preventOverride=0,
        enableBackground=0,
        backgroundColor=(0,0, 0), 
        highlightColor=(0.321569, 0.521569, 0.65098), 
        style="shelf" ,
        horizontal=0)

    # -------------------------------------------------------------------------------------------------
    # ----------------------------------------- RESET CTRLS -------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="resetCtrls_button",
        annotation="Reset ctrls",
        image1="reset_icon.png",
        sourceType="python",
        command="""
from tools import tools_facialRig
tools_facialRig.resetCtrls()
    """
    )

    # -------------------------------------------------------------------------------------------------
    # ---------------------------------------- MIRROR CTRLS -------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="mirrorCtrls_button",
        annotation="Mirror ctrls",
        image1="ruler_icon.png",
        sourceType="python",
        command="""
from tools import tools_facialRig
tools_facialRig.mirrorCtrls()
    """
    )


    # -------------------------------------------------------------------------------------------------
    # ----------------------------------------- LIMIT CTRLS -------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="limitCtrls_button",
        annotation="Limit ctrls",
        image1="lock_icon.png",
        sourceType="python",
        command="""
from tools import tools_facialRig
tools_facialRig.limitCtrls()
    """
    )


    # -------------------------------------------------------------------------------------------------
    # ------------------------------------- CONNECT BLENDSHAPE ----------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="connectCtrls_button",
        annotation="Connect ctrls to blendshape",
        image1="link_icon.png",
        sourceType="python",
        command="""
from tools import tools_facialRig
tools_facialRig.connectBS()
    """
    )


    # -------------------------------------------------------------------------------------------------
    # ---------------------------------------- CTRLS LIBRARY ------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="ctrlsLibrary_button",
        annotation="Controllers library",
        image1="book2_icon.png",
        sourceType="python",
        command="""
    import webbrowser
    webbrowser.open("https://www.google.com")
    """
    )


    # -------------------------------------------------------------------------------------------------
    # ----------------------------------------- COLORS TOOL -------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="colorsTool_button",
        annotation="Colors tool",
        image1="paint_icon.png",
        sourceType="python",
        command="""
    import webbrowser
    webbrowser.open("https://www.google.com")
    """
    )
    # -------------------------------------------------------------------------------------------------
    # ------------------------------------------ SEPARATOR --------------------------------------------
    # -------------------------------------------------------------------------------------------------
    cmds.separator(
        parent=shelf_name,
        enable=1,
        width=12,
        height=35,
        manage=1,
        visible=1,
        preventOverride=0,
        enableBackground=0,
        backgroundColor=(0,0, 0), 
        highlightColor=(0.321569, 0.521569, 0.65098), 
        style="shelf" ,
        horizontal=0)
    
    # -------------------------------------------------------------------------------------------------
    # ----------------------------------------- BUTTON DOC --------------------------------------------
    # -------------------------------------------------------------------------------------------------

    cmds.shelfButton(
        parent=shelf_name,
        label="doc_button",
        annotation="Documentation",
        image1="book_icon.png",
        sourceType="python",
        command="""
import webbrowser
webbrowser.open("https://www.google.com")
    """
    )
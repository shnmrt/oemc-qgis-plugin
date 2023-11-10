# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OemcStac
                                 A QGIS plugin
 This plugin provides easy access to OEMC STAC catalog
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-11-07
        git sha              : $Format:%H$
        copyright            : (C) 2023 by OpenGeoHub
        email                : murat.sahin@opengeohub.org
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .oemc_plugin_dialog import OemcStacDialog
import os.path

# iniital settings for the PYSTAC and STAC_CLIENT
from pathlib import Path
import sys 
sys.path.append(str(Path(__file__).parents[0])+'/src') # findable lib path
from pystac_client.client import Client

#importing the QT libs to control ui
from qgis.core import QgsProject, QgsRasterLayer, QgsTask, QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtWidgets import QListWidget
# to access the qml files on the fly
from urllib.request import urlopen



class OemcStac:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'OemcStac_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&OEMC Plugin')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        ############################################
        # tapping on the project structure to use it
        self.project_tree = QgsProject.instance().layerTreeRoot()
        # saving the stac names and catalog urls as a variable
        self.oemc_stacs = dict(
            OpenLandMap = "https://s3.eu-central-1.wasabisys.com/stac/openlandmap/catalog.json"
        )
        self.strategies = ['Only the selected asset', 'All assets for selected Item(s)', 'Selected Collection']
        

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('OemcStac', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/oemc_plugin/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'OEMC Plugin'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&OEMC Plugin'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = OemcStacDialog()

            # creating some variable to handle the state of the plugin
            self.catalog = None # this will be setted when combobox is triggered
            self.selected = dict() # to store the selected elements
            self.viewed =  dict() # to store the viewed elements
            # stores the XML structure of the qml file to style on the fly w/out downloading
            self.qml_style = dict() 
            self.inserted = list()

        # defining settings for the ui elements on the start
        self.dlg.listCatalog.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # self.dlg.addStrategy.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dlg.listItems.setSelectionMode(QListWidget.ExtendedSelection)
        self.dlg.listAssets.setSelectionMode(QListWidget.ExtendedSelection)
        # adding the stac names from oemc_stac variable
        self.dlg.listCatalog.addItems(list(self.oemc_stacs.keys()))

        # functionalities
        # change on the selection of the catalog will update the 
        # listCatalog and fills it with the collection names
        self.dlg.listCatalog.currentIndexChanged.connect(self.update_collections)
        # based on the selection from collections this will trigered
        # following the selection this will fills the listItems
        self.dlg.listCollection.itemClicked.connect(self.update_items)
        # this will fills the listAssets with unique assets 
        self.dlg.listItems.itemClicked.connect(self.get_unique_assets)
        # this will set selected variable for seleceted assets
        self.dlg.listAssets.itemClicked.connect(self.select_assets)
        # this will fills the strategies wit predefined add layer strategies
        # self.dlg.addStrategy.addItems(self.strategies)
        # finally some one is going to push the addLayers button

        self.dlg.addLayers.clicked.connect(self.add_layers) 

        self.dlg.progressBar.setTextVisible(True)
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        # result = self.dlg.exec_()
        # See if OK was pressed
        # if result:
        #     # Do something useful here - delete the line containing pass and
        #     # substitute with your code.
        #     pass


    def _set_catalog(self,index):
        self.catalog = Client.open(list(self.oemc_stacs.values())[index])
    

    def _get_collection_meta(self, index) :
        '''
        This method used for to collect the title, id, and qml information
        for the selected catalog
        '''
        meta = dict(
            titles = [],
            qmlurls = [],
            ids = []
        )
        for c in self.catalog.get_collections():
            meta['titles'].append(c.title)
            meta['ids'].append(c.id)
            meta['qmlurls'].append(c.to_dict()['qml_url'])
        self.collection_meta = meta
    
    def update_collections(self, index):
        self._set_catalog(index) # setting up the catalog client 
        self._get_collection_meta(index) # setting the catalog meta
        self.dlg.listCollection.addItems(
            sorted(self.collection_meta["titles"])
        )


    def _get_selected_row(self, ui_element):
        # ui_element = self.dlg.listCollection
        sel_index = []
        for i in ui_element.selectedItems():
            sel_index.append(
                ui_element.indexFromItem(i).row()
            )
        return sorted(sel_index)


    def update_items(self):
        '''
        This methods views the items list
        '''
        self.dlg.addLayers.setEnabled(False)
        self.dlg.listItems.clear()
        self.dlg.listAssets.clear()
        selected_name  = sorted(self.collection_meta['titles'])[self._get_selected_row(self.dlg.listCollection)[0]]
        ind = self.collection_meta['titles'].index(selected_name)
        self._update_item_view(ind)
        self.dlg.listItems.addItems(self.viewed['items'])



    def _update_item_view(self,index):
        self.selected['ind'] = index
        self.selected['collection'] = self.collection_meta['ids'][index]
        _items = self.catalog.get_collection(
            self.collection_meta['ids'][index]
        ).get_items()
        self.viewed['items'] = [i.id for i in _items] 


    def get_unique_assets(self):
        self.dlg.addLayers.setEnabled(False)

        uniq_assets = []
        self.update_item()
        for i in self.selected['items']:
            my_memo = self.catalog.get_collection(
                        self.selected['collection']
            ).get_item(i).to_dict()['assets']
            for j in my_memo.keys():
                if not ((j.endswith('view')) or (j.endswith('nail'))):
                    if j not in uniq_assets:
                        uniq_assets.append(j)
        self.viewed['assets'] = uniq_assets
        self.dlg.listAssets.clear()
        self.dlg.listAssets.addItems(self.viewed['assets'])


    def update_item(self):
        selected_items = [] 
        for a in self._get_selected_row(self.dlg.listItems):
            selected_items.append(
                self.viewed['items'][a]
            )
        self.selected['items'] = selected_items


    def select_assets(self):
        selected_assets = []
        for i in self._get_selected_row(self.dlg.listAssets):
            selected_assets.append(
                self.viewed['assets'][i]
            )
        self.selected['assets'] = selected_assets
        self.dlg.addLayers.setEnabled(True)
        

    def get_href(self, collection_id, item_id, asset_id):
        return '/vsicurl/'+self.catalog.get_collection(collection_id)\
            .get_item(item_id)\
            .to_dict()['assets'][asset_id]['href']
    

    def check_style(self, qml_url, qml_name):
        if qml_name not in self.qml_style:
            remote_file = urlopen(qml_url)
            stylebytes  = remote_file.read()
            document = QDomDocument()
            document.setContent(stylebytes)
            self.qml_style[qml_name] = document


    def search_group(self, tree_level, group_name):
        return tree_level.findGroup(group_name)
    

    def insert_layer(self, target, raster, asset, name):
        raster_layer = QgsProject.instance().addMapLayer(
                            QgsRasterLayer(raster, baseName=asset)
        )
        raster_layer.importNamedStyle(self.qml_style[name])
        QgsProject.instance().addMapLayer(mapLayer=raster_layer, addToLegend=False)
        temp_position = QgsProject.instance().layerTreeRoot().findLayer(raster_layer.id())
        target.insertChildNode(-1, temp_position.clone())
        temp_position.parent().removeChildNode(temp_position)

    def check_layers(self, checklist, item):
        res = []
        for i in checklist:
            if item in i:
                res.append(1)
            else:
                res.append(0)
        return res



    
    def add_layers(self):

        total = len(self.selected['assets']) * len(self.selected['items'])
        self.dlg.progressBar.setMaximum(total)
        cnt = 0
        for asset_id in self.selected['assets']:
            for item_id in self.selected['items']:
                qml_url = self.collection_meta['qmlurls'][self.selected['ind']]
                qml_name = qml_url.split('/')[-1]
                self.check_style(qml_url, qml_name)
                
                r_file = self.get_href(self.selected['collection'], item_id, asset_id)
                collection_name = self.collection_meta['titles'][self.selected['ind']]
                collection_tree = self.search_group(self.project_tree, collection_name)
                
                if collection_tree:
                    item_tree = self.search_group(collection_tree, item_id)
                    if item_tree:
                        inserted_layers = item_tree.findLayerIds()
                        if r_file not in self.inserted:
                            self.insert_layer(item_tree, r_file, asset_id, qml_name)
                            self.inserted.append(r_file)

                    else:
                        collection_tree.addGroup(item_id)
                        item_tree = self.search_group(collection_tree, item_id)
                        self.insert_layer(item_tree, r_file, asset_id, qml_name)
                        self.inserted.append(r_file)

                    
                    cnt += 1 
                    self.dlg.progressBar.setValue(cnt)
                else:
                    self.project_tree.addGroup(collection_name)
                    collection_tree = self.search_group(self.project_tree, collection_name)
                    collection_tree.addGroup(item_id)
                    item_tree = self.search_group(collection_tree, item_id)
                    self.insert_layer(item_tree, r_file, asset_id, qml_name)
                    self.inserted.append(r_file)
                    cnt += 1 
                    self.dlg.progressBar.setValue(cnt)

        self.dlg.progressBar.reset()


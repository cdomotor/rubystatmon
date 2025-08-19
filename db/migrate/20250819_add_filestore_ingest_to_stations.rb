# File: db/migrate/20250819_add_filestore_ingest_to_stations.rb
# Path: /db/migrate/20250819_add_filestore_ingest_to_stations.rb
class AddFilestoreIngestToStations < ActiveRecord::Migration[7.1]
  def change
    add_column :stations, :filestore_path,   :string
    add_column :stations, :ingest_enabled,   :boolean, default: false, null: false
    add_column :stations, :ingest_parameters,:text     # JSON stored as text
    add_index  :stations, :ingest_enabled
  end
end

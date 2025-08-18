# File: db/migrate/20250817_add_active_to_stations.rb
# Path: /db/migrate/20250817_add_active_to_stations.rb
class AddActiveToStations < ActiveRecord::Migration[7.1]
  def change
    add_column :stations, :active, :boolean, default: true, null: false
    add_index  :stations, :active
  end
end

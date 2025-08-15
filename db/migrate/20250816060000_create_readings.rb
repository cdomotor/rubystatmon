# File: db/migrate/20250816060000_create_readings.rb
# Path: C:/rubystatmon-fetched/rubystatmon/db/migrate/20250816060000_create_readings.rb

class CreateReadings < ActiveRecord::Migration[7.1]
  def change
    create_table :readings do |t|
      t.references :station, null: false, foreign_key: true, index: true
      t.string  :parameter, null: false
      t.float   :value
      t.datetime :taken_at, null: false

      t.timestamps
    end

    add_index :readings, [:station_id, :parameter, :taken_at]
  end
end

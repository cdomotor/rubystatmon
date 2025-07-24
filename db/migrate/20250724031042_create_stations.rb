class CreateStations < ActiveRecord::Migration[7.1]
  def change
    create_table :stations do |t|
      t.string :name
      t.string :ip_address
      t.string :location
      t.text :notes

      t.timestamps
    end
  end
end

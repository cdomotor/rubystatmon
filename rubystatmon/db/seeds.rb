require 'faker'

10.times do
  Station.create!(
    name: Faker::Name.unique.name,
    ip_address: Faker::Internet.unique.ip_v4_address,
    location: Faker::Address.city,
    notes: Faker::Lorem.sentence
  )
end

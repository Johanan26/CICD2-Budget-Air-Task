# tests/test_users.py
import pytest

def user_payload(username="Sean_Maloney", password="Sean123", firstname="Sean", lastname="Maloney", email="sm@atu.ie", age=22, number="0852012545"):
    return {"username": username, "password": password, "firstname": firstname, "lastname": lastname, "email": email, "age": age, "number": number}

#testing to see if user is created properly
def test_create_user_ok(client):
    r = client.post("/api/users", json=user_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "Sean_Maloney"
    assert data["email"] == "sm@atu.ie"
    assert data["age"] == 22

def test_user_id_generated(client):
    r1 = client.post("/api/users", json=user_payload(username="Sean"))
    r2 = client.post("/api/users", json=user_payload(username="Mary", email="no@gmail.com"))
    assert r1.status_code == 201 #201 = created successful
    assert r2.status_code == 201
    assert r1.json()["user_id"] != r2.json()["user_id"]

# COME BACK TO THIS, WE NEED TO MAKE A PASSPORT TYPE CHECK
# #testing for bad student ids using parameterized test
# @pytest.mark.parametrize("bad_sid", ["BAD123", "s1234567", "S123", "S12345678"])
# def test_bad_student_id_422(client, bad_sid):
#  r = client.post("/api/users", json=user_payload(uid=3, sid=bad_sid))
#  assert r.status_code == 422 # pydantic validation error

#testing to see if users can be got
def test_get_user_404(client):
    r = client.get("/api/users/999")
    # pydantic validation error
    assert r.status_code == 404 #404 = Not found

#testing to see if user can be deleted
def test_delete_then_404(client):
    client.post("/api/users", json=user_payload(username="Deleteme"))

    r2 = client.delete(f"api/users/Deleteme")
    assert r2.status_code == 204 #204 = no content

    r3 = client.delete(f"/api/users/Deleteme")
    assert r3.status_code == 404
 
 #Testing Put(Update)
def test_update_then_404(client):
    # Create a new user
    r1 = client.post("/api/users", json=user_payload(username="Sean"))
    user_data = r1.json() #instead of just checking user id we will check user data, so the full response, only way I can get it to work without it breaking
    # it's converting the response we get into the python dictionary, it contains all the data that got returned from the response 
    # Create updated user payload
    update_payload = user_payload(username="UpdatedSean")
    #line below takes the username field form the original response (user_data['username'])
    #then the update payload sends back the updated user details
    r2 = client.put(f"/api/users/Sean", json=update_payload)
    assert r2.status_code == 200 #request succesful
    r3 = client.put("/api/users/BA999999", json=user_payload())

    assert r3.status_code == 404
from fastapi import APIRouter, HTTPException,UploadFile, File, Form
from typing import List
import os,shutil

from database_functions import (
    get_all_user_preferences,add_user_preferences,get_user_preferences_by_user,
    get_all_user_privacy_settings,add_user_privacy_settings,get_user_privacy_settings_by_user,
    get_user,get_all_users,add_user,delete_user,add_user_photo_files
    )

from schemas import (
    Operation_Out,
    User_Preference_List,User_Privacy_List,
    AdminCreateRequest
    )

PHOTO_DIR = "storage/user"
os.makedirs(PHOTO_DIR, exist_ok=True)

#region User
def getUserRouter():
    user_router=APIRouter(tags=["User"],prefix="/user")

    @user_router.post("")
    def Add_user(user_data: AdminCreateRequest):
        return {"success":add_user(user_data.username)}
    
    @user_router.get("")
    def Get_All_Users():
        return get_all_users()
    
    @user_router.delete("/{username}")
    def Delete_User(username:str):
        return {"success":delete_user(username)}

    @user_router.get("/preferences")
    def Get_All_Preferences():
        preferences=get_all_user_preferences()
        res=[]
        for user in preferences:
            res.append({"user_id":user["user_id"],"preferences":user["preferences"].split(",")})
        return res
    
    @user_router.get("/preferences/{username}")
    def Get_Preferences_Of_Single_User(username:str):
        user= get_user_preferences_by_user(username)
        return {"user_id":user["user_id"],"preferences":user["preferences"].split(",")} if user else {}
    
    @user_router.put("/preferences",response_model=Operation_Out)
    def Add_User_Preferences(preferences_list:User_Preference_List):
        to_add=[]
        for user in preferences_list.data:
            to_add.append((user.user_id,','.join(user.preferences)))
        return {"success":add_user_preferences(to_add)}
    
    @user_router.get("/privacy")
    def Get_All_Privacy_settings():
        preferences=get_all_user_privacy_settings()
        res=[]
        for user in preferences:
            res.append({"user_id":user["user_id"],"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])})
        return res
    
    @user_router.get("/privacy/{user_id}")
    def Get_Privacy_Setting_Of_Single_User(user_id:str):
        user= get_user_privacy_settings_by_user(user_id)
        return {"user_id":user["user_id"],"data_collection":bool(user["data_collection"]),"data_disclosure":bool(user["data_disclosure"])} if user else {}
    
    @user_router.put("/privacy",response_model=Operation_Out)
    def Add_User_Privacy_Settings(privacy_list:User_Privacy_List):
        to_add=[]
        for user in privacy_list.data:
            to_add.append((user.user_id,user.data_collection,user.data_disclosure))
        return {"success":add_user_privacy_settings(to_add)}
    

    @user_router.post("/photo")
    async def Upload_User_Photo(files: List[UploadFile] = File(...), usernames: List[str] = Form(...)):
        """
        Riceve una lista di file e i corrispondenti piani,
        salva i file su disco e inserisce i record nel DB.
        Il frontend invia: files=[file0, file1, ...] floors=[0, 1, ...]
        """
        saved = []
        for username, file in zip(usernames, files):
            ext = file.filename.split(".")[-1]
            filename = f"user_{username}.{ext}"
            path = os.path.join(PHOTO_DIR, filename)

            with open(path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            url = f"storage/user/{filename}"
            add_user_photo_files([( url,username)])
            saved.append({"username": username, "url": url})

        return saved

    
    return user_router
#endregion
